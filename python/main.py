import requests
from aes import cryptoEncode
from pyquery import PyQuery as pq
from urllib.parse import quote
import subprocess
import json
import sys

base = "http://100.100.9.2"
hd = {
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}
u = "xxxxx"
p = "xxxxx"
se = requests.session()
se.headers.update(hd)


def get_wan_ip():
    """从 OpenWrt WAN 口获取 IP 地址"""
    try:
        # 方法1: 使用 ubus 命令（推荐）
        result = subprocess.run(
            ["ubus", "call", "network.interface.wan", "status"],
            capture_output=True,
            text=True,
            check=True
        )
        wan_info = json.loads(result.stdout)
        ip_address = wan_info['ipv4-address'][0]['address']
        return ip_address
    except Exception as e:
        print(f"方法1失败: {e}")
        try:
            # 方法2: 使用 ip 命令
            result = subprocess.run(
                ["ip", "-4", "addr", "show", "eth0"],  # eth1 通常是 WAN 口，根据实际情况修改
                capture_output=True,
                text=True,
                check=True
            )
            # 解析输出获取 IP
            for line in result.stdout.split('\n'):
                if 'inet ' in line:
                    ip_address = line.strip().split()[1].split('/')[0]
                    return ip_address
        except Exception as e2:
            print(f"方法2失败: {e2}")
            try:
                # 方法3: 读取网络配置文件
                result = subprocess.run(
                    ["ifconfig", "eth0"],  # 根据实际 WAN 口接口名修改
                    capture_output=True,
                    text=True,
                    check=True
                )
                for line in result.stdout.split('\n'):
                    if 'inet addr:' in line:
                        ip_address = line.split('inet addr:')[1].split()[0]
                        return ip_address
                    elif 'inet ' in line:
                        ip_address = line.strip().split()[1]
                        return ip_address
            except Exception as e3:
                print(f"方法3失败: {e3}")
                raise ValueError("无法获取 WAN 口 IP 地址")


def login(u, p):
    # 获取 WAN 口 IP
    wan_ip = get_wan_ip()
    print(f"获取到的 WAN IP: {wan_ip}")
    
    # 使用获取到的 IP 构建 URL
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
