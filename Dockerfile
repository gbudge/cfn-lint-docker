#
# For those that prefer to use Alpine, here is a Dockerfile for cfn-lint
#
ARG BASE_IMAGE_REPO=public.ecr.aws/docker/library/python
ARG BASE_IMAGE_TAG=3.13-alpine3.20
ARG BASE_IMAGE_DIGEST=sha256:40a4559d3d6b2117b1fbe426f17d55b9100fa40609733a1d0c3f39e2151d4b33

FROM ${BASE_IMAGE_REPO}:${BASE_IMAGE_TAG}@${BASE_IMAGE_DIGEST}

RUN pip install cfn-lint[full]
RUN pip install pydot

ENTRYPOINT ["cfn-lint"]
CMD ["--help"]
