@echo off
title CloakBrowser - Profile aaaaa (Port 4023)
cd /d "D:\Dev\rev-flow"
echo Dang khoi chay CloakBrowser tren cong 4023...
"C:\Users\ngkie\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe" --fingerprint=39707912 --fingerprint-platform=windows --ignore-gpu-blocklist --webrtc-ip-handling-policy=disable_non_proxied_udp --user-data-dir="D:\Dev\rev-flow\browser_vault\aaaaa\user_data" --remote-debugging-port=4023 --remote-allow-origins=* --fingerprint-timezone=Asia/Ho_Chi_Minh --lang=en-US --fingerprint-locale=en-US --start-maximized --new-window "https://flow.google.com/project/006f6e93-2d22-4a3d-9b03-1a902a50fd10"
