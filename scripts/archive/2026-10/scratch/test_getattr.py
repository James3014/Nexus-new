import astropy.coordinates as coord
import sys

class custom_coord(coord.SkyCoord):
    @property
    def prop(self):
        return getattr(self, 'random_attr')

try:
    c = custom_coord('00h42m30s', '+41d12m00s', frame='icrs')
    c.prop
except AttributeError as e:
    print("Caught:", type(e), e)
