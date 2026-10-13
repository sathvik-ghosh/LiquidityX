FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py ./
COPY liquidityx ./liquidityx
COPY .streamlit ./.streamlit
# Platforms such as Render/Railway/Fly/Cloud Run inject $PORT; default 8501 locally.
EXPOSE 8501
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"]
