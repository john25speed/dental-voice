FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 5055
CMD ["gunicorn", "--bind", "0.0.0.0:5055", "--workers", "2", "server:app"]
