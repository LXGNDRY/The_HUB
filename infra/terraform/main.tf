terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = { source = "hashicorp/google"  version = "~> 6.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_service_account" "worker" {
  account_id   = "hub-worker"
  display_name = "The HUB durable worker"
}

resource "google_cloud_run_v2_job" "worker" {
  name     = "hub-worker"
  location = var.region
  template {
    template {
      service_account = google_service_account.worker.email
      max_retries     = 3
      timeout         = "900s"
      containers {
        image   = var.worker_image
        command = ["python", "-m", "app.workers.main"]
      }
    }
  }
}

resource "google_pubsub_topic" "jobs" { name = "hub-jobs" }
resource "google_pubsub_topic" "dead_letter" { name = "hub-jobs-dead-letter" }
