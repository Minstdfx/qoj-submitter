# qoj-submitter
Use submit command to submit problem during qoj contests.
## ~~Training Mode not Supported Yet~~
现在应该支持火车模式了
## Usage
1. 安装油猴脚本
2. 启动本地服务器 `python server.py`
3. 打开比赛页面 `https://qoj.ac/contest/*`并保持该窗口活动
4. windows：配置Powershell别名 `function submit { python ".\submit.py" @args }`
5. linux：配置别名 `echo 'alias submit="python3 /绝对路径/submit.py"' >> ~/.bashrc & source ~/.bashrc`
6. 打开选手文件夹终端，创建 `A.cpp` 或 `qwq.cpp`，使用 `submit A.cpp` 或 `submit qwq.cpp -p B -y`
