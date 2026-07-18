In an integration module, extend the selection and scope your behaviour:

```python
class AiBridge(models.Model):
    _inherit = "ai.bridge"

    provider = fields.Selection(
        selection_add=[("myruntime", "My Runtime")],
        ondelete={"myruntime": "set default"},
    )


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    def _add_extra_payload_fields(self, payload):
        payload = super()._add_extra_payload_fields(payload)
        if self.ai_bridge_id.provider != "myruntime":
            return payload
        # provider-specific payload changes here
        return payload
```

On the bridge form, select the provider matching the target runtime. Bridges
left as `Generic` keep the upstream behaviour.
