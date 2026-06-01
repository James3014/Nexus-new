import re

file_path = "scratch/tmp_astropy_14096/astropy/coordinates/attributes.py"
content = open(file_path).read()

old_code = """    def __get__(self, instance, frame_cls=None):
        if instance is None:
            out = self.default
        else:
            out = getattr(instance, "_" + self.name, self.default)
            if out is None:
                out = getattr(instance, self.secondary_attribute, self.default)

        out, converted = self.convert_input(out)
        if instance is not None:
            # None if instance (frame) has no data!
            instance_shape = getattr(instance, "shape", None)
            if instance_shape is not None and (
                getattr(out, "shape", ()) and out.shape != instance_shape
            ):
                # If the shapes do not match, try broadcasting.
                try:
                    if isinstance(out, ShapedLikeNDArray):
                        out = out._apply(
                            np.broadcast_to, shape=instance_shape, subok=True
                        )
                    else:
                        out = np.broadcast_to(out, instance_shape, subok=True)
                except ValueError:
                    # raise more informative exception.
                    raise ValueError(
                        f"attribute {self.name} should be scalar or have shape"
                        f" {instance_shape}, but it has shape {out.shape} and could not"
                        " be broadcast."
                    )

                converted = True

            if converted:
                setattr(instance, "_" + self.name, out)

        return out"""

new_code = """    def __get__(self, instance, frame_cls=None):
        try:
            if instance is None:
                out = self.default
            else:
                out = getattr(instance, "_" + self.name, self.default)
                if out is None:
                    out = getattr(instance, self.secondary_attribute, self.default)

            out, converted = self.convert_input(out)
            if instance is not None:
                # None if instance (frame) has no data!
                instance_shape = getattr(instance, "shape", None)
                if instance_shape is not None and (
                    getattr(out, "shape", ()) and out.shape != instance_shape
                ):
                    # If the shapes do not match, try broadcasting.
                    try:
                        if isinstance(out, ShapedLikeNDArray):
                            out = out._apply(
                                np.broadcast_to, shape=instance_shape, subok=True
                            )
                        else:
                            out = np.broadcast_to(out, instance_shape, subok=True)
                    except ValueError:
                        # raise more informative exception.
                        raise ValueError(
                            f"attribute {self.name} should be scalar or have shape"
                            f" {instance_shape}, but it has shape {out.shape} and could not"
                            " be broadcast."
                        )

                    converted = True

                if converted:
                    setattr(instance, "_" + self.name, out)

            return out
        except AttributeError as e:
            raise e from None"""

if old_code in content:
    open(file_path, "w").write(content.replace(old_code, new_code))
    print("Patched 14B!")
else:
    print("Not found")
