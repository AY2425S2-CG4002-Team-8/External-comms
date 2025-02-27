class FOVManager:
    def __init__(self):
        self.fov_data = None

    def set_fov(self, fov: bool):
        self.fov_data = fov

    def get_fov(self):
        return self.fov_data
    
    def handle_fov(self, fov: str) -> None:
        if not int(fov):
            self.set_fov(False)
        else:
            self.set_fov(True)
            