FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5012
CMD ["gunicorn", "-b", "0.0.0.0:5012", "app:app"]
