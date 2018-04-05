FROM python:3

LABEL maintainer="Probably nobody :(" \
      contributors="Mathias Sass Michno <m@michno.me>"

ENV PYTHONUNBUFFERED 1
RUN mkdir -p /usr/src/get5-web/instance
# Copy application
COPY requirements.txt /usr/src/get5-web/
COPY get5 /usr/src/get5-web/get5
COPY migrations /usr/src/get5-web/migrations
COPY gunicorn.conf /usr/src/get5-web/gunicorn.conf
WORKDIR /usr/src/get5-web
RUN pip3 install -r requirements.txt

EXPOSE 8000
CMD gunicorn --config /usr/src/get5-web/gunicorn.conf -b :8000 get5:app
