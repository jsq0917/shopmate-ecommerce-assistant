# 生产反代公共片段：由 web/nginx.prod.conf 在 /api/ 与 /api/v1/auth/ 中 include。
#
# 单独成文件是为了让两条 location 的代理语义完全一致；修改时必须同步 docs/08-deployment.md。
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;

# SSE：关掉缓冲与缓存，长连接不设 60s 空闲上限。
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;

# 后端把登录相关 cookie 的 Path 设为 /api/v1/auth，页面 JS 在 / 下读不到
# shopmate_csrf，静默刷新会失败；与前端 vite 代理保持一致，重写为 /。
proxy_cookie_path /api/v1/auth /;

# 知识文档上传上限（应用侧另有 KNOWLEDGE_UPLOAD_MAX_BYTES 校验）。
client_max_body_size 25m;

proxy_hide_header X-Powered-By;
