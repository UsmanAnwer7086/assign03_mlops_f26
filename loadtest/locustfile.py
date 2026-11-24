from locust import HttpUser, between, task


class ApiUser(HttpUser):
    wait_time = between(0.01, 0.1)

    @task(3)
    def predict(self):
        self.client.post("/predict", json={"forecast_days": 7})

    @task(1)
    def health(self):
        self.client.get("/health")
