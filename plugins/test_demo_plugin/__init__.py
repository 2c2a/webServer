from plugins.core.base import PluginInterface

class TestDemoPlugin(PluginInterface):
    def __init__(self):
        super().__init__(
            plugin_id='test_demo',
            name='Test Demo Plugin',
            version='0.1.0',
            description='A test plugin for verifying zip installation',
        )

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> bool:
        return True
