# 訂單管理系統 (Order Management System) API 協議定義
# Version: v1.0.0
# Domain: BDD Modeling & API Contract

## 1. 資源模型 (Resource Model)
- **Order**:
    - `id`: string (UUID)
    - `customer_id`: string (UUID)
    - `items`: List<OrderItem>
    - `total_amount`: decimal
    - `status`: enum (PENDING, PAID, SHIPPED, COMPLETED, CANCELLED)
    - `created_at`: timestamp
    - `updated_at`: timestamp

- **OrderItem**:
    - `product_id`: string (UUID)
    - `quantity`: integer
    - `unit_price`: decimal

## 2. API 端點 (API Endpoints)

### Create Order
- **POST** `/v1/orders`
- **Request Body**:
  ```json
  {
    "customer_id": "uuid",
    "items": [
      {
        "product_id": "uuid",
        "quantity": 1
      }
    ]
  }
  ```
- **Success Response**: `201 Created` with Order object.

### Get Order
- **GET** `/v1/orders/{order_id}`
- **Success Response**: `200 OK` with Order object.

### Update Order Status
- **PATCH** `/v1/orders/{order_id}/status`
- **Request Body**:
  ```json
  {
    "status": "PAID"
  }
  ```
- **Success Response**: `200 OK` with updated Order object.

## 3. BDD 契約場景 (BDD Contract Scenarios)
- **Feature**: Order Creation
  - **Scenario**: Successful order creation with valid items
    - **Given** a valid customer ID and stock available for products
    - **When** a POST request is sent to `/v1/orders`
    - **Then** the response status should be 201
    - **And** the order status should be "PENDING"
