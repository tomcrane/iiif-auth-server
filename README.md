# iiif-auth-server

A demo server implementation of all aspects of the [IIIF Authorization Flow API 2.0](https://iiif.io/api/auth/2.0/). It shows:

* The active interaction pattern (as a login, a clickthrough, and an "I am not a robot" test)
* The kiosk interaction pattern
* The external interaction pattern (including a time-based example)
* Probe services, including degraded access via the probe's `substitute`
* Access services shared between resources
* Access control on IIIF Image API 3 services, and on content resources that aren't services: video, audio, MPEG-DASH, PDF and 3D
* Access token and logout services

This is a work in progress, please raise issues! It is intended to assist client development by providing a live implementation to test against.

It's a Flask app with a deliberately small [IIIF Image API 3](https://iiif.io/api/image/3.0/) implementation (`iiifauth/image_api.py`, using Pillow). It generates [IIIF Presentation 3](https://iiif.io/api/presentation/3.0/) Manifests and a Collection for the examples from `iiifauth/auth2_media_config.json`.

There is an accompanying JavaScript client application to run against the server demo at [https://github.com/tomcrane/iiif-auth-client](https://github.com/tomcrane/iiif-auth-client).

This is not a production application! A typical institutional implementation would likely protect many thousands of images with the same access services, whereas this demo makes you authenticate for most of the sample images separately. It also gives access to everyone's session for diagnostic purposes, has one hardcoded username and password (`username` / `password`) for the login pattern, and so on. However, it should exercise every part of the specification.

## Two clients: first-party and third-party

The access services in this specification rely on the browser sending cookies with requests for the content - e.g., an `<img>` or `<video>` element's `src`. When the client is on a different _site_ from the server, those are _third-party_ cookies, and many browsers now block or partition them.

So the home page links to two copies of the same iiif-auth-client code:

* **First-party** - on the same site as this server, e.g. `client.example.org` alongside `iiifauth.example.org`, or a path on the same domain. Set `IIIFAUTH_FIRST_PARTY_CLIENT_URL` to its URL. iiif-auth-client has a Docker image for this.
* **Third-party** - [on GitHub Pages](https://tomcrane.github.io/iiif-auth-client/) by default (`IIIFAUTH_THIRD_PARTY_CLIENT_URL`). Its cookies are subject to the browser's policy for third-party cookies.

A site is the scheme plus the registrable domain, ignoring the port - so when you're developing locally, a client on `http://localhost:8080` is first-party to a server on `http://localhost:5000`.

## Usage

1. Clone this repo
2. (optional) In the iiif-auth-server directory, set up a virtualenv:
```
python3 -m venv venv
```
3. To install for development:
```
pip install --editable .
```
4. to run for _local_ development with an ad-hoc SSL cert:
```
export FLASK_APP=iiifauth
export FLASK_DEBUG=true
flask run --cert=adhoc
```
or
```
. runflask.sh
```

This will give nasty warnings about the SSL but works without having to do anything further. It _must_ be run over https, otherwise `SameSite=None; Secure` cookies will be ignored by browsers. (Chrome treats `http://localhost` as secure, so `flask run` without a certificate also works there.)

To try a first-party client locally, serve a copy of iiif-auth-client from another port on localhost, using the same scheme as the server. For example, in Chrome, run the server with plain `flask run`, run `python -m http.server 8080` in the client's directory (or use its Docker image), and visit `http://localhost:8080/?collection=http://localhost:5000/collection.json`.

5. Token information is stored in a sqlite3 db which initialises itself.

## Configuration

| Environment variable | Purpose |
| --- | --- |
| `IIIFAUTH_SECRET_KEY` | Signs the Flask session cookie. Set this to a random value when hosting. |
| `IIIFAUTH_DATABASE_FILE` | Where to keep the sqlite token database. Defaults to `iiifauth/iiifauth.db`. |
| `IIIFAUTH_FIRST_PARTY_CLIENT_URL` | URL of a copy of iiif-auth-client on the same site as this server, linked from the home page. |
| `IIIFAUTH_THIRD_PARTY_CLIENT_URL` | URL of a copy on a different site. Defaults to the GitHub Pages copy. |
| `IIIFAUTH_SERVER_NAME` | Optional; Flask's `SERVER_NAME`. |

## Docker

The `Dockerfile` builds an image for hosting, e.g. on AWS ECS / Fargate. It runs gunicorn on port 8000, as a non-root user.

```
docker build -t iiif-auth-server .
docker run -p 8000:8000 -e IIIFAUTH_SECRET_KEY=change-me iiif-auth-server
```

Then visit http://localhost:8000/ (Chrome treats `localhost` as secure, so the `Secure` cookies work there without https).

### Running on ECS / Fargate

* **TLS**: terminate it at the load balancer. The app trusts `X-Forwarded-Proto` (and `X-Forwarded-Host`, if present) from the proxy in front of it, so the ids it generates are https URLs on the public host name. ALB passes the original `Host` header through; if you put CloudFront in front, forward the `Host` header to the origin.
* **One task**: the token database is a sqlite file inside the container. Run a single task, or enable sticky sessions on the target group, otherwise a token issued by one task won't be recognised by another. Losing the database when a task is replaced is fine; users just log in again.
* **Secret**: supply `IIIFAUTH_SECRET_KEY` from Secrets Manager or Parameter Store in the task definition.
* **Health check**: `/index.json` returns 200.
* **First-party client**: run iiif-auth-client's image as a second service on the same site, e.g. a sibling subdomain, or a path on the same domain using an ALB path rule. Set `IIIFAUTH_FIRST_PARTY_CLIENT_URL` to its URL.

## Publishing to Amazon ECR

`.github/workflows/docker.yml` builds the image for every pull request and push, to check that it still builds. Once it's configured, it also pushes the image to ECR from `master` (tagged `latest` and `sha-<commit>`) and from `v*` tags (tagged with the version). iiif-auth-client has the same workflow.

The workflow signs in to AWS with GitHub's OIDC tokens, so there are no AWS keys stored in GitHub. To set it up, with the AWS CLI:

1. If your AWS account doesn't already have GitHub's OIDC identity provider (IAM > Identity providers), add it:
   ```
   aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com
   ```
2. Create the ECR repositories:
   ```
   aws ecr create-repository --repository-name iiif-auth-server
   aws ecr create-repository --repository-name iiif-auth-client
   ```
   The workflow moves the `latest` tag, so don't turn on tag immutability, or remove `latest` from the workflow.
3. Create a role that only these two repositories' `master` branches and `v*` tags can assume. Save this as `trust.json`, with your account id:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": {"Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"},
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": {
         "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
         "StringLike": {"token.actions.githubusercontent.com:sub": [
           "repo:tomcrane/iiif-auth-server:ref:refs/heads/master",
           "repo:tomcrane/iiif-auth-server:ref:refs/tags/v*",
           "repo:tomcrane/iiif-auth-client:ref:refs/heads/master",
           "repo:tomcrane/iiif-auth-client:ref:refs/tags/v*"
         ]}
       }
     }]
   }
   ```
   and this as `ecr-push.json`, with your region and account id:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {"Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
       {"Effect": "Allow", "Action": [
           "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:InitiateLayerUpload",
           "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"],
        "Resource": [
           "arn:aws:ecr:<region>:<account-id>:repository/iiif-auth-server",
           "arn:aws:ecr:<region>:<account-id>:repository/iiif-auth-client"]}
     ]
   }
   ```
   then:
   ```
   aws iam create-role --role-name iiif-auth-github-ecr --assume-role-policy-document file://trust.json
   aws iam put-role-policy --role-name iiif-auth-github-ecr --policy-name ecr-push --policy-document file://ecr-push.json
   ```
4. Tell each GitHub repository where to push, with repository variables (Settings > Secrets and variables > Actions > Variables), or with the GitHub CLI:
   ```
   gh variable set AWS_ROLE_ARN --repo tomcrane/iiif-auth-server --body arn:aws:iam::<account-id>:role/iiif-auth-github-ecr
   gh variable set AWS_REGION --repo tomcrane/iiif-auth-server --body <region>
   gh variable set ECR_REPOSITORY --repo tomcrane/iiif-auth-server --body iiif-auth-server
   ```
   and the same for `tomcrane/iiif-auth-client`, with `ECR_REPOSITORY` set to `iiif-auth-client`.

Until `AWS_ROLE_ARN` is set, the workflow only builds. It builds for `linux/amd64`; to build for Graviton as well, set a `DOCKER_PLATFORMS` variable to `linux/amd64,linux/arm64` (this is slower, as the arm64 build is emulated).

The workflow only publishes images. Updating the ECS services to run a new image is up to you.
