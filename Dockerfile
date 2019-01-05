FROM python:3.7

# Creating working directory
RUN mkdir -p /app/src
WORKDIR /app/src

RUN apt-get update && apt-get install -y ffmpeg
RUN pip install pipenv

# Expose webhook port
EXPOSE 443

# Creating environment
COPY Pipfile /app/src
COPY Pipfile.lock /app/src
RUN pipenv install

# Copy app
COPY . /app/src

CMD [ "pipenv", "run", "python", "main.py" ]
