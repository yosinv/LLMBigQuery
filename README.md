# LLMBigQuery

# Natural Language → SQL -> answer in Natural Language

### 

Welcome to BigQuery LLM and SQLAlchemy project which uses LLMs to democratize access to data analysis over BigQuery. 

## :thinking: How it works:
you can ask any question on your data in natural language, while in the backend a SQL is being generated and natural language is returned. 

##still in development



in sqlalchemy_bigquery modification need to be done based on the code shared:
https://support.teradata.com/community?id=community_question&sys_id=ffd453e0dbc3e810e91893b5b996193d

updated code:
  super(BigQueryCompiler, self).__init__(dialect=dialect, statement=statement, column_keys=column_keys,
                                                **kwargs)
instead:
  super(BigQueryCompiler, self).__init__(dialect, statement, column_keys, inline, **kwargs)
