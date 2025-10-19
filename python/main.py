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

WAN_DEVICE = "eth0"  # ← 改成你的实际网卡名（可能是 eth0, eth1, pppoe-wan 等）


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
        
        # 检查是否有 IPv4 地址
        if 'ipv4-address' in wan_info and len(wan_info['ipv4-address']) > 0:
            return wan_info['ipv4-address'][0]['address']
        
        # 如果没有，尝试从 ip addr 命令获取
        result = subprocess.run(
            ["ip", "-4", "addr", "show", WAN_DEVICE],
            capture_output=True,
            text=True,
            timeout=5
        )
        # 解析输出，找到 inet 行
        for line in result.stdout.split('\n'):
            if 'inet ' in line:
                ip = line.strip().split()[1].split('/')[0]
                return ip
        
        return None
    except Exception as e:
        print(f"[错误] 获取 WAN IP 失败: {e}")
        return None


def refresh_network():
    """通过网卡 down/up 刷新网络（模拟重新插拔网线）"""
    try:
        print("[网络] 重启网卡以刷新 ARP 缓存...")
        
        # down 网卡
        subprocess.run(['ip', 'link', 'set', WAN_DEVICE, 'down'], 
                      timeout=5, check=False)
        time.sleep(2)
        
        # up 网卡
        subprocess.run(['ip', 'link', 'set', WAN_DEVICE, 'up'], 
                      timeout=5, check=False)
        
        # 等待接口恢复
        print("[网络] 等待网卡恢复...")
        time.sleep(5)
        
        # 检查 IP 是否恢复
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


def login(u, p):
    # 先刷新网络
    refresh_network()
    
    # 获取 WAN 口 IP
    wan_ip = get_wan_ip()
    if not wan_ip:
        print("[错误] 无法获取 WAN IP，退出")
        return
    
    print(f"[登录] 使用 IP: {wan_ip}")
    
    try:
        res = se.get(base + f"/gportal/web/login?wlanuserip={wan_ip}&wlanacname=GiWiFi_lnsfHG")
        doc = pq(res.text)
        doc("#loginForm input[name=user_account]").val(u)
        doc("#loginForm input[name=user_password]").val(p)
        data = "&".join([
            f"{el.attr('name')}={quote(el.val())}"
            for el in doc("#loginForm input").items()
        ])
        msg = cryptoEncode(data, doc("input[name=iv]").attr("value"))
        msg = "&".join([f"{k}={quote(v)}" for k, v in msg.items()])
        res = se.post(base + "/gportal/Web/loginAction", data=msg)
        print(res.text)
    except Exception as e:
        print(f"[错误] 登录失败: {e}")


def logout():
    si = get_si()
    data = {"si": si}
    res = se.post(base + "/gportal/Web/logoutAction", data=data)
    print(res.text)


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
