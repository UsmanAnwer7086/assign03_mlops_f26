"""Kubeflow Pipelines (KFP v2) definition: ingest -> features -> train.

Every step is a container component running the same image that is pushed by CI/CD.
Compile with:  python kubeflow/btc_kfp_pipeline.py   -> btc_kfp_pipeline.yaml
"""

import os

from kfp import compiler, dsl

IMAGE = os.getenv("KFP_IMAGE", "YOUR_DOCKERHUB_USER/btc-forecast:latest")


@dsl.container_component
def ingest_data(raw_data: dsl.Output[dsl.Dataset]):
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["python", "-m", "src.etl_fetch"],
        args=["--out", raw_data.path],
    )


@dsl.container_component
def build_features(raw_data: dsl.Input[dsl.Dataset], features: dsl.Output[dsl.Dataset]):
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["python", "-m", "src.preprocess"],
        args=["--inp", raw_data.path, "--out", features.path],
    )


@dsl.container_component
def train_model(features: dsl.Input[dsl.Dataset], model: dsl.Output[dsl.Model]):
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["python", "-m", "src.train_forecast"],
        args=["--data", features.path, "--model-dir", model.path],
    )


@dsl.pipeline(name="btc-forecast-pipeline", description="Daily BTC-USD 7-day forecast training")
def btc_pipeline():
    ingest = ingest_data()
    feats = build_features(raw_data=ingest.outputs["raw_data"])
    train_model(features=feats.outputs["features"])


if __name__ == "__main__":
    compiler.Compiler().compile(btc_pipeline, package_path="btc_kfp_pipeline.yaml")
    print("Compiled -> btc_kfp_pipeline.yaml")
