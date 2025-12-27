import requests
from aes import cryptoEncode
from pyquery import PyQuery as pq
from urllib.parse import quote
import subprocess
import json
import sys
import time

base = "http://100.100.9.2"
hd = {
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}
u = "xxxxxx"
p = "xxxxxx"
se = requests.session()
se.headers.update(hd)

WAN_DEVICE = "eth0"  # ← 根据自己的网卡名称修改


def get_wan_ip():
    """从 OpenWrt WAN 口获取 IP 地址"""
    try:
        result = subprocess.run(
            ["ubus", "call", "network.interface.wan", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        wan_info = json.loads(result.stdout)
        
        if 'ipv4-address' in wan_info and len(wan_info['ipv4-address']) > 0:
            return wan_info['ipv4-address'][0]['address']
        
        result = subprocess.run(
            ["ip", "-4", "addr", "show", WAN_DEVICE],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'inet ' in line:
                ip = line.strip().split()[1].split('/')[0]
                return ip
        
        return None
    except Exception as e:
        print(f"[错误] 获取 WAN IP 失败: {e}")
        return None


def refresh_network():
    """通过网卡 down/up 刷新网络"""
    try:
        print("[网络] 重启网卡以刷新 ARP 缓存...")
        subprocess.run(['ip', 'link', 'set', WAN_DEVICE, 'down'], 
                      timeout=5, check=False)
        time.sleep(5)
        subprocess.run(['ip', 'link', 'set', WAN_DEVICE, 'up'], 
                      timeout=5, check=False)
        print("[网络] 等待网卡恢复...")
        time.sleep(3.5)
        
        for i in range(10):
            ip = get_wan_ip()
            if ip:
                print(f"[网络] 网卡已恢复，IP: {ip}")
                return True
            time.sleep(1)
        
        print("[网络] 警告：网卡未获取到 IP，继续尝试认证...")
        return False
    except Exception as e:
        print(f"[网络] 刷新失败: {e}")
        return False


def do_auth_request(wan_ip, u, p):
    """
    执行单次登录请求逻辑
    返回: response 对象
    """
    try:
        # 1. 获取登录页，拿到 token/iv 等信息
        login_page_url = base + f"/gportal/web/login?wlanuserip={wan_ip}&wlanacname=GiWiFi_lnsfHG"
        res = se.get(login_page_url)
        doc = pq(res.text)
        
        # 2. 填充表单
        doc("#loginForm input[name=user_account]").val(u)
        doc("#loginForm input[name=user_password]").val(p)
        
        # 3. 加密数据
        data = "&".join([
            f"{el.attr('name')}={quote(el.val())}"
            for el in doc("#loginForm input").items()
        ])
        
        # 注意：这里假设 cryptoEncode 返回的是字典
        iv_val = doc("input[name=iv]").attr("value")
        if not iv_val:
            # 有时候页面加载失败没有IV，直接返回原页面内容供上层判断
            return res 
            
        msg = cryptoEncode(data, iv_val)
        msg_str = "&".join([f"{k}={quote(v)}" for k, v in msg.items()])
        
        # 4. 发送 POST
        post_res = se.post(base + "/gportal/Web/loginAction", data=msg_str)
        return post_res
        
    except Exception as e:
        print(f"[内部错误] 构造请求失败: {e}")
        return None


def login(u, p):
    # 1. 先执行物理层面的网络刷新（只做一次）
    refresh_network()
    
    # 2. 获取 IP
    wan_ip = get_wan_ip()
    if not wan_ip:
        print("[错误] 无法获取 WAN IP，退出")
        return
    
    print(f"[登录] 使用 IP: {wan_ip} 开始认证...")
    
    # 3. 第一次尝试登录
    res = do_auth_request(wan_ip, u, p)
    if not res:
        return

    # 4. 解析结果，检查是否需要绑定
    try:
        # 尝试解析 JSON
        res_json = res.json()
        
        # 检查是否命中“绑定设备”的逻辑 (Status 0 + ResultCode 124)
        if res_json.get("status") == 0 and res_json.get("data", {}).get("resultCode") == 124:
            info_msg = res_json.get('info', '需要验证设备')
            print(f"[提示] {info_msg}")
            
            # 获取绑定链接
            # 服务器返回的 resultData 类似于: /Giportal/index.php/Sta/bindSta?token=...
            bind_path = res_json['data']['resultData']
            full_bind_url = base + bind_path
            
            print(f"[绑定] 检测到新设备，正在请求绑定接口: {full_bind_url}")
            
            # 请求绑定接口
            bind_res = se.get(full_bind_url)
            print(f"[绑定] 服务器响应: {bind_res.text}")
            
            # 绑定后，通常需要再次发送登录包
            print("[绑定] 绑定操作完成，正在自动重试登录...")
            time.sleep(7) # 稍等7s让服务器同步状态
            
            # 5. 再次尝试登录 (Retry)
            retry_res = do_auth_request(wan_ip, u, p)
            if retry_res:
                print(f"[最终结果] {retry_res.text}")
                
        else:
            # 正常的成功或普通失败
            print(f"[结果] {res.text}")
            
    except json.JSONDecodeError:
        # 如果返回的不是 JSON（可能是 HTML 错误页或已经登录成功的页面）
        print(f"[结果] 非JSON响应: {res.text}")
    except Exception as e:
        print(f"[异常] 处理响应时出错: {e}")


def logout():
    try:
        si = get_si()
        data = {"si": si}
        res = se.post(base + "/gportal/Web/logoutAction", data=data)
        print(res.text)
    except Exception as e:
        print(f"[注销失败] {e}")


def get_si():
    res = se.get(base + "/gportal/web/logout")
    doc = pq(res.text)
    si = doc("input[name=si]").attr("value")
    if not si:
        raise ValueError("Failed to retrieve 'si'")
    return si


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "logout":
        logout()
    else:
        login(u, p)