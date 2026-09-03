FROM python:3.11-slim

WORKDIR /app

# সিস্টেম ডিপেনডেন্সি
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# পাইথন ডিপেনডেন্সি ইনস্টল করা
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# বাকি সব ফাইল কপি করা
COPY . .

# Cloud Run / MCPize ডিফল্ট পোর্ট ৮০৮০ এক্সপোজ করা
ENV PORT=8080
EXPOSE 8080

# সার্ভার চালু করার কমান্ড
CMD ["python", "server.py"]