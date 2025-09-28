# Base Image
FROM python:3.12-slim

WORKDIR /app
ENV FLASK_APP=main
ENV FLASK_ENV=development

# install dependencies
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

EXPOSE 8000

# Start command
CMD ["flask", "run", "--debug"]