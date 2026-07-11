# Render 免费部署

## 重要限制

- 免费 Web Service 闲置后会休眠，休眠期间不会监控行情或发送预警。
- 免费实例使用临时文件系统。重启、重新部署或休眠后，网页中新增的预警、历史记录和邮件设置可能丢失。
- 部署包已经清空邮箱密码。请勿把真实密码提交到公开仓库。

## 部署步骤

1. 将本目录上传到 GitHub 仓库。
2. 登录 Render，选择 **New > Blueprint**。
3. 连接该 GitHub 仓库；Render 会读取 `render.yaml`。
4. 按提示填写：
   - `APP_USERNAME`：网页登录用户名。
   - `APP_PASSWORD`：强密码，建议至少 16 位。
5. 创建服务并等待部署完成。
6. 打开 Render 提供的 `onrender.com` 地址，浏览器会弹出用户名和密码输入框。

无需填写 `SECRET_KEY`，Render 会自动生成。

