FROM python:3.11-slim

RUN pip install --no-cache-dir \
    mlflow \
    boto3 \
    psycopg2-binary

EXPOSE 5000

CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000"]
