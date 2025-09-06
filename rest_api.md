# Google Access Context Manager API

This document provides a summary of the REST resources and methods for the Google Access Context Manager API. This API allows you to create and manage access control policies, including access levels and service perimeters, for your Google Cloud resources.

## Service Endpoint

All API URIs are relative to the following base URL:

```
[https://accesscontextmanager.googleapis.com](https://accesscontextmanager.googleapis.com)
```

---

## API Version: v1

This section details the stable `v1` endpoints for the Access Context Manager API.

### Resource: `v1.accessPolicies`

Manages access policies for an organization.

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `create` | `POST /v1/accessPolicies` | Creates an access policy. |
| `delete` | `DELETE /v1/{name=accessPolicies/*}` | Deletes an access policy based on its resource name. |
| `get` | `GET /v1/{name=accessPolicies/*}` | Returns an access policy based on its name. |
| `getIamPolicy` | `POST /v1/{resource=accessPolicies/*}:getIamPolicy` | Gets the IAM policy for the specified access policy. |
| `list` | `GET /v1/accessPolicies` | Lists all access policies in an organization. |
| `patch` | `PATCH /v1/{policy.name=accessPolicies/*}` | Updates an access policy. |
| `setIamPolicy` | `POST /v1/{resource=accessPolicies/*}:setIamPolicy` | Sets the IAM policy for the specified access policy. |
| `testIamPermissions` | `POST /v1/{resource=accessPolicies/*}:testIamPermissions`| Returns the IAM permissions the caller has on the resource. |

### Resource: `v1.accessPolicies.accessLevels`

Manages access levels within an access policy.

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `create` | `POST /v1/{parent=accessPolicies/*}/accessLevels` | Creates an access level. |
| `delete` | `DELETE /v1/{name=accessPolicies/*/accessLevels/*}` | Deletes an access level based on its resource name. |
| `get` | `GET /v1/{name=accessPolicies/*/accessLevels/*}` | Gets an access level based on its resource name. |
| `list` | `GET /v1/{parent=accessPolicies/*}/accessLevels` | Lists all access levels for an access policy. |
| `patch` | `PATCH /v1/{accessLevel.name=accessPolicies/*/accessLevels/*}` | Updates an access level. |
| `replaceAll` | `POST /v1/{parent=accessPolicies/*}/accessLevels:replaceAll` | Replaces all existing access levels in a policy. |
| `testIamPermissions` | `POST /v1/{resource=accessPolicies/*/accessLevels/*}:testIamPermissions`| Returns the IAM permissions the caller has on the resource. |

### Resource: `v1.accessPolicies.authorizedOrgsDescs`

Manages authorized organization descriptions.

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `create` | `POST /v1/{parent=accessPolicies/*}/authorizedOrgsDescs` | Creates an authorized organizations description. |
| `delete` | `DELETE /v1/{name=accessPolicies/*/authorizedOrgsDescs/*}` | Deletes an authorized organizations description. |
| `get` | `GET /v1/{name=accessPolicies/*/authorizedOrgsDescs/*}` | Gets an authorized organizations description. |
| `list` | `GET /v1/{parent=accessPolicies/*}/authorizedOrgsDescs` | Lists all authorized organizations descriptions for a policy. |
| `patch` | `PATCH /v1/{authorizedOrgsDesc.name=accessPolicies/*/authorizedOrgsDescs/*}` | Updates an authorized organizations description. |

### Resource: `v1.accessPolicies.servicePerimeters`

Manages service perimeters within an access policy.

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `commit` | `POST /v1/{parent=accessPolicies/*}/servicePerimeters:commit` | Commits the dry-run specification for all service perimeters. |
| `create` | `POST /v1/{parent=accessPolicies/*}/servicePerimeters` | Creates a service perimeter. |
| `delete` | `DELETE /v1/{name=accessPolicies/*/servicePerimeters/*}` | Deletes a service perimeter based on its resource name. |
| `get` | `GET /v1/{name=accessPolicies/*/servicePerimeters/*}` | Gets a service perimeter based on its resource name. |
| `list` | `GET /v1/{parent=accessPolicies/*}/servicePerimeters` | Lists all service perimeters for an access policy. |
| `patch` | `PATCH /v1/{servicePerimeter.name=accessPolicies/*/servicePerimeters/*}` | Updates a service perimeter. |
| `replaceAll` | `POST /v1/{parent=accessPolicies/*}/servicePerimeters:replaceAll` | Replaces all existing service perimeters in a policy. |
| `testIamPermissions` | `POST /v1/{resource=accessPolicies/*/servicePerimeters/*}:testIamPermissions`| Returns the IAM permissions the caller has on the resource. |

### Resource: `v1.operations`

Manages long-running operations.

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `cancel` | `POST /v1/{name=operations/**}:cancel` | Starts asynchronous cancellation on a long-running operation. |
| `delete` | `DELETE /v1/{name=operations/**}` | Deletes a long-running operation. |
| `get` | `GET /v1/{name=operations/**}` | Gets the latest state of a long-running operation. |
| `list` | `GET /v1/{name=operations}` | Lists operations that match the specified filter. |

### Resource: `v1.organizations.gcpUserAccessBindings`

Manages GCP user access bindings for an organization.

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `create` | `POST /v1/{parent=organizations/*}/gcpUserAccessBindings` | Creates a GcpUserAccessBinding. |
| `delete` | `DELETE /v1/{name=organizations/*/gcpUserAccessBindings/*}` | Deletes a GcpUserAccessBinding. |
| `get` | `GET /v1/{name=organizations/*/gcpUserAccessBindings/*}` | Gets the GcpUserAccessBinding with the given name. |
| `list` | `GET /v1/{parent=organizations/*}/gcpUserAccessBindings` | Lists all GcpUserAccessBindings for an organization. |
| `patch` | `PATCH /v1/{gcpUserAccessBinding.name=organizations/*/gcpUserAccessBindings/*}` | Updates a GcpUserAccessBinding. |

### Resource: `v1.services`

Lists services supported by VPC Service Controls.

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `get` | `GET /v1/services/{name}` | Returns a VPC-SC supported service based on the service name. |
| `list` | `GET /v1/services` | Lists all VPC-SC supported services. |

---

## API Version: v1alpha

This section details the alpha release endpoints. These are subject to change and are not recommended for production use.

### Resource: `v1alpha.accessPolicies`

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `create` | `POST /v1alpha/accessPolicies` | Creates an access policy. |
| `delete` | `DELETE /v1alpha/{name=accessPolicies/*}` | Deletes an access policy based on the resource name. |
| `get` | `GET /v1alpha/{name=accessPolicies/*}` | Returns an access policy based on the name. |
| `getIamPolicy` | `POST /v1alpha/{resource=accessPolicies/*}:getIamPolicy` | Gets the IAM policy for the specified access policy. |
| `list` | `GET /v1alpha/accessPolicies` | Lists all access policies in an organization. |
| `patch` | `PATCH /v1alpha/{policy.name=accessPolicies/*}` | Updates an access policy. |
| `setIamPolicy` | `POST /v1alpha/{resource=accessPolicies/*}:setIamPolicy` | Sets the IAM policy for the specified access policy. |
| `testIamPermissions` | `POST /v1alpha/{resource=accessPolicies/*}:testIamPermissions`| Returns the IAM permissions the caller has on the resource. |

### Resource: `v1alpha.accessPolicies.accessLevels`

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `create` | `POST /v1alpha/{parent=accessPolicies/*}/accessLevels` | Creates an access level. |
| `delete` | `DELETE /v1alpha/{name=accessPolicies/*/accessLevels/*}` | Deletes an access level based on the resource name. |
| `get` | `GET /v1alpha/{name=accessPolicies/*/accessLevels/*}` | Gets an access level based on the resource name. |
| `list` | `GET /v1alpha/{parent=accessPolicies/*}/accessLevels` | Lists all access levels for an access policy. |
| `patch` | `PATCH /v1alpha/{accessLevel.name=accessPolicies/*/accessLevels/*}` | Updates an access level. |
| `replaceAll` | `POST /v1alpha/{parent=accessPolicies/*}/accessLevels:replaceAll` | Replaces all existing access levels in a policy. |
| `testIamPermissions` | `POST /v1alpha/{resource=accessPolicies/*/accessLevels/*}:testIamPermissions`| Returns the IAM permissions the caller has on the resource. |

### Resource: `v1alpha.accessPolicies.authorizedOrgsDescs`

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `create` | `POST /v1alpha/{parent=accessPolicies/*}/authorizedOrgsDescs` | Creates an authorized organizations description. |
| `delete` | `DELETE /v1alpha/{name=accessPolicies/*/authorizedOrgsDescs/*}` | Deletes an authorized organizations description. |
| `get` | `GET /v1alpha/{name=accessPolicies/*/authorizedOrgsDescs/*}` | Gets an authorized organizations description. |
| `list` | `GET /v1alpha/{parent=accessPolicies/*}/authorizedOrgsDescs` | Lists all authorized organizations descriptions for a policy. |
| `patch` | `PATCH /v1alpha/{authorizedOrgsDesc.name=accessPolicies/*/authorizedOrgsDescs/*}` | Updates an authorized organizations description. |

### Resource: `v1alpha.accessPolicies.servicePerimeters`

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `commit` | `POST /v1alpha/{parent=accessPolicies/*}/servicePerimeters:commit` | Commits the dry-run specification for all service perimeters. |
| `create` | `POST /v1alpha/{parent=accessPolicies/*}/servicePerimeters` | Creates a service perimeter. |
| `delete` | `DELETE /v1alpha/{name=accessPolicies/*/servicePerimeters/*}` | Deletes a service perimeter based on the resource name. |
| `get` | `GET /v1alpha/{name=accessPolicies/*/servicePerimeters/*}` | Gets a service perimeter based on the resource name. |
| `list` | `GET /v1alpha/{parent=accessPolicies/*}/servicePerimeters` | Lists all service perimeters for an access policy. |
| `patch` | `PATCH /v1alpha/{servicePerimeter.name=accessPolicies/*/servicePerimeters/*}` | Updates a service perimeter. |
| `replaceAll` | `POST /v1alpha/{parent=accessPolicies/*}/servicePerimeters:replaceAll` | Replaces all existing service perimeters in a policy. |
| `testIamPermissions` | `POST /v1alpha/{resource=accessPolicies/*/servicePerimeters/*}:testIamPermissions`| Returns the IAM permissions the caller has on the resource. |

### Resource: `v1alpha.operations`

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `get` | `GET /v1alpha/{name=operations/**}` | Gets the latest state of a long-running operation. |

### Resource: `v1alpha.organizations.gcpUserAccessBindings`

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `create` | `POST /v1alpha/{parent=organizations/*}/gcpUserAccessBindings` | Creates a GcpUserAccessBinding. |
| `delete` | `DELETE /v1alpha/{name=organizations/*/gcpUserAccessBindings/*}` | Deletes a GcpUserAccessBinding. |
| `get` | `GET /v1alpha/{name=organizations/*/gcpUserAccessBindings/*}` | Gets the GcpUserAccessBinding with the given name. |
| `list` | `GET /v1alpha/{parent=organizations/*}/gcpUserAccessBindings` | Lists all GcpUserAccessBindings for an organization. |
| `patch` | `PATCH /v1alpha/{gcpUserAccessBinding.name=organizations/*/gcpUserAccessBindings/*}` | Updates a GcpUserAccessBinding. |

### Resource: `v1alpha.services`

| Method | HTTP Request | Description |
| :--- | :--- | :--- |
| `get` | `GET /v1alpha/services/{name}` | Get a VPC-SC Supported Service by name. |
| `list` | `GET /v1alpha/services` | Lists all VPC-SC supported services. |
