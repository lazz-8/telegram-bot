FROM python:3.11-slim

# تثبيت ffmpeg + أدوات مهمة
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

# تحديث pip أولاً
RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
