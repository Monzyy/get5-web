FROM alpine:3.7

LABEL maintainer="Probably nobody :(" \
      contributors="Mathias Sass Michno <m@michno.me>"

# Copy application
COPY requirements.txt /usr/src/get5-web/
COPY get5/ /usr/src/get5-web/get5/
COPY instance/prod_config.py /usr/src/get5-web/instance/prod_config.py
COPY main.py /usr/src/get5-web/
COPY manager.py /usr/src/get5-web/
COPY logging.conf /usr/src/get5-web/logging.conf
COPY gunicorn.conf /usr/src/get5-web/gunicorn.conf

# Install dependencies
RUN apk --no-cache --update add \
        python3 gunicorn bash shadow sudo && \
    apk --no-cache add --virtual .build-dependencies \
        python3-dev poppler-dev gcc g++ && \
# Install python dependencies
    python3 -m ensurepip && \
    rm -r /usr/lib/python*/ensurepip && \
    cd /usr/src/get5-web && \
    pip3 install --no-cache-dir -r requirements.txt && \
# Remove build dependencies
    apk del .build-dependencies && \
# Create user
    chmod +x manage.py && \
    ./manage.py db upgrade

WORKDIR /usr/src/get5-web
# Mount volumes and set Entrypoint
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/gunicorn"]
CMD ["--config", "/usr/src/get5-web/gunicorn.conf", "--log-config", "/usr/src/get5-web/logging.conf", "-b", ":8000", "get5:app"]
