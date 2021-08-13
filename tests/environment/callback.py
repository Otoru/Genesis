from typing import Dict, Union, List


class Callback:
    """
    Class used to represent a callback.
    """

    def __init__(self):
        self.event: Dict[str, Union[str, List[str]]] = {}
        self.control = False

    async def __await__(self, *args, **kwargs):
        return self

    def __call__(self, event: Dict[str, Union[str, List[str]]], *args, **kwargs):
        self.event = event
        self.control = True
