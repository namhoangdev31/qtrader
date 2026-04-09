FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.111.1 uvicorn==0.30.6 pydantic==2.8.2
COPY main.py ./main.py
EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
