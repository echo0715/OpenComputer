# Project Phoenix Technical Specification

## Overview

Project Phoenix is an internal REST API that exposes user and account operations
for the billing platform. This document describes the public surface and the
data model used by the service.

## Goals

- Provide a stable, versioned HTTP API.
- Enforce strict input validation on all endpoints.
- Emit structured logs for every request.

## Non-Goals

- Replacing the existing identity provider.
- Providing a graphical UI.
