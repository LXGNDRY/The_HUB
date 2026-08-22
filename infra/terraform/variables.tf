variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "worker_image" {
  type = string
}

variable "github_repository" {
  type    = string
  default = "LXGNDRY/The_HUB"
}
