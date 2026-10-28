import requests
from aes import cryptoEncode
from pyquery import PyQuery as pq
from urllib.parse import quote
import subprocess
import json
import sys
import time
import re

base = "http://100.100.9.2"
hd = {
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}
u = "xxxxx"
p = "xxxxx"
student_id = "xxxxx"  # ← 填学工号
se = requests.session()
se.headers.update(hd)

WAN_DEVICE = "eth1"  # ← 填网口


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
            f"{el.attr('name')}={quote(el.val() or '')}"
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


def complete_user_info(info_url, stu_id, u=None, p=None):
    """
    处理完善个人信息流程 (ResultCode 40)
    1. 访问完善信息页获取 iv、页面预填的真实姓名 (identity_name) 及提交接口地址
    2. 填入顶端配置的学工号 (identity_no)，AES 加密后 POST 提交
    """
    try:
        full_info_url = info_url if info_url.startswith("http") else base + info_url
        print(f"[信息完善] 正在访问个人信息页面: {full_info_url}")
        res = se.get(full_info_url)
        doc = pq(res.text)

        # 提取加密 IV
        iv_val = doc("#formData input[name=iv]").val() or doc("#iv").attr("value")
        if not iv_val:
            print("[错误] 无法从个人信息页面获取加密 IV")
            return False

        # 填充学工号（真实姓名 identity_name 由页面服务端预填，保留原值）
        doc("#formData input[name=identity_no]").val(stu_id)

        # 构造 #formData 序列化参数 (如: iv=xxx&identity_name=xxx&identity_no=xxx)
        data = "&".join([
            f"{el.attr('name')}={quote(el.val() or '')}"
            for el in doc("#formData input").items()
            if el.attr("name")
        ])

        # 从页面脚本中提取包含动态 rand 参数的提交路径
        m = re.search(r'(/Giportal/index\.php/user/completeUserInfo\?rand=\d+)', res.text)
        submit_path = m.group(1) if m else "/Giportal/index.php/user/completeUserInfo"
        submit_url = base + submit_path

        msg = cryptoEncode(data, iv_val)
        msg_str = "&".join([f"{k}={quote(v)}" for k, v in msg.items()])

        print(f"[信息完善] 正在提交学工号 ({stu_id}) 至: {submit_url}")
        post_res = se.post(submit_url, data=msg_str)
        print(f"[信息完善] 服务器响应: {post_res.text}")

        res_json = post_res.json()
        if res_json.get("status") == 1:
            print(f"[信息完善] {res_json.get('info', '完善用户信息完成!')}")
            return True

        # 若返回 data == '1001'，表示当前学/工号已被其他账户绑定，附上原账号密码重新绑定
        if str(res_json.get("data")) == "1001" and u and p:
            print("[信息完善] 检测到当前学/工号已被其他账户绑定，正在尝试附带账号密码解绑并重绑...")
            rebind_data = f"{data}&old_account={quote(u)}&old_password={quote(p)}"
            rebind_msg = cryptoEncode(rebind_data, iv_val)
            rebind_msg_str = "&".join([f"{k}={quote(v)}" for k, v in rebind_msg.items()])
            rebind_res = se.post(submit_url, data=rebind_msg_str)
            print(f"[信息完善] 重绑响应: {rebind_res.text}")
            rebind_json = rebind_res.json()
            if rebind_json.get("status") == 1:
                return True

        print(f"[错误] 完善个人信息失败: {res_json.get('info', '未知错误')}")
        return False

    except Exception as e:
        print(f"[异常] 完善个人信息过程出错: {e}")
        return False


def bind_device(bind_path):
    """
    处理新设备绑定流程 (ResultCode 124)
    注意：HAR 捕获显示前端通过 $.post(resultData, {}) 发起 POST 请求
    """
    try:
        full_bind_url = bind_path if bind_path.startswith("http") else base + bind_path
        print(f"[绑定] 检测到新设备，正在请求绑定接口: {full_bind_url}")
        bind_res = se.post(full_bind_url, data={})
        print(f"[绑定] 服务器响应: {bind_res.text}")
        return True
    except Exception as e:
        print(f"[异常] 绑定设备出错: {e}")
        return False


def login(u, p, stu_id=student_id):
    # 1. 先执行物理层面的网络刷新（只做一次）
    refresh_network()
    
    # 2. 获取 IP
    wan_ip = get_wan_ip()
    if not wan_ip:
        print("[错误] 无法获取 WAN IP，退出")
        return
    
    print(f"[登录] 使用 IP: {wan_ip} 开始认证...")
    
    # 3. 发起首次登录请求
    res = do_auth_request(wan_ip, u, p)
    if not res:
        return

    try:
        res_json = res.json()

        # 4. 检查是否命中“请先完善您的个人信息!” (Status 0 + ResultCode 40)
        if res_json.get("status") == 0 and str(res_json.get("data", {}).get("resultCode")) == "40":
            info_msg = res_json.get("info", "请先完善您的个人信息!")
            print(f"[提示] {info_msg}")
            info_url = res_json["data"]["resultData"]

            if complete_user_info(info_url, stu_id, u, p):
                print("[信息完善] 个人信息完善成功，等待 3 秒后重新发起登录认证...")
                time.sleep(3)
                res = do_auth_request(wan_ip, u, p)
                if not res:
                    return
                res_json = res.json()
            else:
                return

        # 5. 检查是否命中“绑定设备”的逻辑 (Status 0 + ResultCode 124)
        if res_json.get("status") == 0 and str(res_json.get("data", {}).get("resultCode")) == "124":
            info_msg = res_json.get("info", "需要验证设备")
            print(f"[提示] {info_msg}")
            
            bind_path = res_json["data"]["resultData"]
            if bind_device(bind_path):
                print("[绑定] 绑定操作完成，正在自动重试登录...")
                time.sleep(5)
                
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
        login(u, p, student_id)