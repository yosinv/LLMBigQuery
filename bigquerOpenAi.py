import os
from pathlib import Path

import pandas as pd
from langchain import OpenAI, SQLDatabase, SQLDatabaseChain
from sqlalchemy import *
from sqlalchemy.engine import create_engine
from sqlalchemy import select, func, Integer, Table, Column, MetaData
from sqlalchemy.schema import *
from google.cloud import bigquery
from google.cloud import bigquery
from google.oauth2 import service_account
from pybigquery.api import ApiClient
from dotenv import load_dotenv

# TODO(developer): Set key_path to the path to the service account key
#                  file.
key_path = "yourjason key file"

# V2 BIGQUERY CLIENT LIB
credentials = service_account.Credentials.from_service_account_file(
    key_path, scopes=["https://www.googleapis.com/auth/cloud-platform"],
)
client = bigquery.Client(credentials=credentials, project=credentials.project_id,)
def query_result(client,QUERY:str)->None:
    query_job = client.query(QUERY)  # API request
    rows = query_job.result()  # Waits for query to finish
    for row in rows:
        print(row)

# V3
from google.oauth2 import service_account
credentials = service_account.Credentials.from_service_account_file(key_path)
# print(credentials.project_id)
# engine = create_engine('bigquery://', credentials_info=credentials)

# V4
SQLALCHEMY_SILENCE_UBER_WARNING=1
engine = create_engine('bigquery://<projectname>',credentials_path=key_path)
conn = engine.connect()
# print(conn)

# Perform a query. - TEST connect to BQ is working
QUERY = ('SELECT current_date()')
query_result(client,QUERY)

# SQL ALCHEMY
metadata = MetaData()
table = Table('<dataset>>.<table>', metadata)
# TEST BIGQUERY ALCHEMY
# print(select([func.count('*')], from_obj=table).scalar())

# LLM BIGQUERY SQLALCHEMY
os.environ["GOOGLE_APPLICATION_CREDENTIALS"]=key_path
print(os.environ['GOOGLE_APPLICATION_CREDENTIALS'])

# LOADING OPENAI from .ENV
dotenv_path = Path('<path>/.env')
load_dotenv(dotenv_path=dotenv_path)


db = SQLDatabase.from_uri('bigquery://<project>')
llm = OpenAI(temperature=0)  #OpenAI
db_chain = SQLDatabaseChain(llm=OpenAI(), database=db)
# print(db_chain)
print(db_chain.run({"query" :"<your question>" }))
# db_chain.run("How many cogs are there?")
