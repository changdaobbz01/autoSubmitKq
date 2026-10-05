FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css app.js /usr/share/nginx/html/
RUN chmod 0644 /etc/nginx/conf.d/default.conf \
    /usr/share/nginx/html/index.html \
    /usr/share/nginx/html/styles.css \
    /usr/share/nginx/html/app.js

EXPOSE 80
