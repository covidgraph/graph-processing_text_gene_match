FROM python:3.7

RUN mkdir /src

COPY run.py /src/
COPY requirements.txt /src/

WORKDIR /src

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH="/src:${PYTHONPATH}"

CMD ["python", "run.py"]