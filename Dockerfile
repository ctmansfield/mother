FROM python:3.11-slim
WORKDIR /app
COPY mother_app/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY mother_app /app/mother_app
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "mother_app.main:app", "--host", "0.0.0.0", "--port", "8080"]
