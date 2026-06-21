FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Forces Uvicorn web boot instead of Eel desktop boot
CMD ["python", "main.py", "--web"]