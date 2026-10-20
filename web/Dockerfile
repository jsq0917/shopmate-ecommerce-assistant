FROM nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10

COPY nginx.conf /etc/nginx/nginx.conf
COPY public/ /usr/share/nginx/html/

RUN chown -R nginx:nginx /usr/share/nginx/html

USER nginx

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD ["wget", "-q", "-O", "-", "http://127.0.0.1:8080/healthz"]

CMD ["nginx", "-g", "daemon off;"]
