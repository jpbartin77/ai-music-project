# Route to Add when using the dCloud FP Workplace Lab

## Add Static Route

To enable connectivity to the dCloud FP Workplace lab environment, add the following static route:

| Property | Value |
|----------|-------|
| Destination | `10.0.0.0/8` |
| Gateway | `<dCloud_Gateway_IP>` |
| Metric | `1` |

## Commands

**Linux/macOS:**
```bash
sudo route add -net 10.0.0.0/8 gw <dCloud_Gateway_IP>
```

**Windows:**
```cmd
route add 10.0.0.0 mask 255.0.0.0 <dCloud_Gateway_IP>
```

Replace `<dCloud_Gateway_IP>` with your dCloud lab gateway IP address.
