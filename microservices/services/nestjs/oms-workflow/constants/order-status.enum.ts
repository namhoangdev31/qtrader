export enum OrderStatus {
  PENDING = 'PENDING',        // Created in Control Plane, not yet routed
  ROUTED = 'ROUTED',          // Dispatched to Compute Plane
  ACKNOWLEDGED = 'ACK',       // Received by Compute Plane/Rust Core
  PARTIALLY_FILLED = 'PARTIAL',
  FILLED = 'FILLED',
  CANCELLED = 'CANCELLED',
  REJECTED = 'REJECTED',
  EXPIRED = 'EXPIRED',
}
