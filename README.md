# iiif-auth-server

A stripped down version of [IIIF Authentication specification](http://iiif.io/api/auth/1.0/), just to explore third-party cookie issues.

There is an accompanying JavaScript client application to run against the server demo at [https://github.com/tomcrane/iiif-auth-client](https://github.com/tomcrane/iiif-auth-client).

This is not a production application! A typical institutional implementation would likely protect many thousands of images with the same cookie and token services, whereas this demo makes you authenticate for most of the sample images separately. It also gives access to everyone's session for diagnostic purposes, has one hardcoded username and password for Login pattern cookie services, and so on. However, it should exercise every part of the specification.


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
This will give nasty warnings about the SSL but works without having to do anything further. It _must_ be run over https, even locally, otherwise `SameSite`, `Secure` cookies will be ignored by browsers.

5. Token information is stored in a sqllite3 db which should initialise itself 
