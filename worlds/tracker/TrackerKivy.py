from kivy.core.image import ImageLoader, ImageLoaderBase, ImageData
from kivy.uix.image import AsyncImage
from typing import List, Union
import pkgutil
import io


class ImageLoaderPkgutil(ImageLoaderBase):
    def load(self, filename: str) -> List[ImageData]:
        # take off the "ap:" prefix
        module, path = filename[3:].split("/", 1)
        data = pkgutil.get_data(module, path)
        print(filename)
        return self._bytes_to_data(data)

    def _bytes_to_data(self, data: Union[bytes, bytearray]) -> List[ImageData]:
        loader=next(loader for loader in ImageLoader.loaders if loader.can_load_memory())
        return loader.load(loader, io.BytesIO(data))
    
class ApAsyncImage(AsyncImage):
    def is_uri(self, filename: str) -> bool:
        if filename.startswith("ap:"):
            return True
        else:
            return super().is_uri(filename)

# grab the default loader method so we can override it but use it as a fallback
_original_image_loader_load = ImageLoader.load


def load_override(filename: str, default_load=_original_image_loader_load, **kwargs):
    if filename.startswith("ap:"):
        return ImageLoaderPkgutil(filename)
    else:
        return default_load(filename, **kwargs)

ImageLoader.load = load_override
