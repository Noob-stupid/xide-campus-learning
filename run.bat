@echo off
cd /d %~dp0
if not exist data\zhixue.db (
  echo [习得] 首次运行，生成演示数据...
  python seed.py --reset
)
echo [习得] http://127.0.0.1:5820
python app.py
