## LNU GIWIFI 认证脚本

forked from [mcitem/GIWIFI](https://github.com/mcitem/GIWIFI)

对Python脚本做出一些修改 识别wan口的IP，并填入认证链接部分 增加网口热插拔功能

By Claude4.5-sonnet

使用方法：

把main.py中u和p变量修改为你自己的宽带账号

在Openwrt配置python环境

把依赖打上，在机器内执行main.py login/logout即可（可能需要clone mac地址）

附定时执行方法：

新建一个sh脚本并给execute权限，内容如下

```sh
#!/bin/sh
cd /path/to/your/python/script/directory
exec /usr/bin/python3 your_python_script.py login >> /path/to/your/log/directory.log 2>&1
```

在Openwrt计划任务(crontab)插件添加以下内容

```
SHELL=/bin/sh
PATH=/usr/sbin:/usr/bin:/sbin:/bin
0 8 * * * /path/to/your/sh/dir.sh
```

0 8 * * * 为cron表达式 可自行修改执行时间
