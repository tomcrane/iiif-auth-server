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

## Two clients: same origin and cross-site

The access services in this specification rely on the browser sending cookies with requests for the content - e.g., an `<img>` or `<video>` element's `src`. When the client is on a different site from the server, those are _third-party_ cookies, and many browsers now block or partition them.

So the home page links to two copies of iiif-auth-client:

* **Same origin** - served from this server at `/client/`. The cookies are first-party.
* **Cross-site** - [on GitHub Pages](https://tomcrane.github.io/iiif-auth-client/). The cookies are third-party, and subject to the browser's policy for them.

The server serves the client from the `client` directory next to the `iiifauth` package, or from the directory in the `IIIFAUTH_CLIENT_DIR` environment variable. The Render build (below) clones it there.

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

To use the same-origin client locally, either clone iiif-auth-client into `./client`, or point `IIIFAUTH_CLIENT_DIR` at your copy:
```
export IIIFAUTH_CLIENT_DIR=../iiif-auth-client
```
then visit `/client/?collection=<this server>/collection.json`.

5. Token information is stored in a sqlite3 db which initialises itself.

## Configuration

| Environment variable | Purpose |
| --- | --- |
| `IIIFAUTH_SECRET_KEY` | Signs the Flask session cookie. Set this to a random value when hosting. |
| `IIIFAUTH_SERVER_NAME` | Optional; Flask's `SERVER_NAME`. |
| `IIIFAUTH_CLIENT_DIR` | Where to find the copy of iiif-auth-client to serve at `/client/`. |

## Hosting

The repo includes a [Render](https://render.com) Blueprint, `render.yaml`. In the Render dashboard, choose **New > Blueprint** and select this repo. It runs on the free plan, which spins down after 15 minutes without traffic and takes about a minute to wake up. The local disk is wiped when it spins down, which loses the token database - users just have to log in again.

The build clones iiif-auth-client (the branch in `IIIFAUTH_CLIENT_REF`, default `master`) into `./client`.

Run a single instance: the token database is a local sqlite file. The app trusts `X-Forwarded-Proto` and `X-Forwarded-Host` from the proxy in front of it, so the ids it generates are https URLs on the public host name.

`Procfile` has the same start command, for other hosts that use one.
