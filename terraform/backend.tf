terraform {
  backend "s3" {
    # bucket, key, and region are supplied via -backend-config at init time.
    use_lockfile = true
    encrypt      = true
  }
}
