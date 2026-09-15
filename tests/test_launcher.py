"""
启动.bat 冒烟测试

用途：不改动系统环境的前提下，验证批处理能被 cmd 正确解析（不出现
      "不是内部或外部命令" 的乱码报错），并能把服务拉起来。

用法：
    python tests/test_launcher.py          # 只负责启动，不等它结束
    然后另开一条命令看端口/日志（见 README「启动」一节）

注意：批处理里的 `pause` 会等按键，所以这里不能让 shell 等它结束，
      必须后台拉起、外部轮询。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAT = os.path.join(HERE, "启动.bat")
LOG = os.path.join(HERE, "_batch_test.log")


def main():
    if not os.path.exists(BAT):
        print("找不到 启动.bat：", BAT)
        return 1
    env = dict(os.environ)
    env["XQ_NO_BROWSER"] = "1"          # 测试时不要弹浏览器
    with open(LOG, "w", encoding="utf-8") as fh:
        p = subprocess.Popen(["cmd", "/c", BAT], cwd=HERE,
                             stdout=fh, stderr=subprocess.STDOUT, env=env)
    print(f"已用 cmd 拉起 启动.bat，cmd PID = {p.pid}")
    print(f"输出写入 {LOG}")
    print("等待约 8 秒后检查端口 8760 是否在监听。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
