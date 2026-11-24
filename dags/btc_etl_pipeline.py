"""Daily BTC-USD ETL -> retrain -> evaluate -> notify API DAG."""

import os
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator

default_args = {
    "owner": "mlops",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def fetch_data():
    from src.etl_fetch import run

    return run()


def preprocess():
    from src.preprocess import run

    return run()


def train_and_evaluate():
    import pandas as pd

    from src.train_forecast import train_and_register

    data_dir = os.environ["DATA_DIR"]
    df = pd.read_csv(os.path.join(data_dir, "processed", "btc_features.csv"))
    result = train_and_register(df, os.environ["MODEL_DIR"])
    return result  # pushed to XCom; contains "passed" and the metrics


def model_passed(ti):
    result = ti.xcom_pull(task_ids="train_and_evaluate")
    return bool(result and result.get("passed"))


def reload_api():
    resp = requests.post(
        os.environ["API_RELOAD_URL"],
        headers={"X-Reload-Token": os.environ["RELOAD_TOKEN"]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


with DAG(
    dag_id="btc_etl_pipeline",
    description="Daily BTC-USD fetch, feature engineering, retraining and API reload",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    tags=["btc", "mlops"],
) as dag:
    t_fetch = PythonOperator(task_id="fetch_data", python_callable=fetch_data)
    t_prep = PythonOperator(task_id="preprocess_features", python_callable=preprocess)
    t_train = PythonOperator(task_id="train_and_evaluate", python_callable=train_and_evaluate)
    t_gate = ShortCircuitOperator(task_id="check_threshold", python_callable=model_passed)
    t_reload = PythonOperator(task_id="reload_api_model", python_callable=reload_api)

    t_fetch >> t_prep >> t_train >> t_gate >> t_reload
