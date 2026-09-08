class TaskManager:
    ENERGY_PER_STEP = 0.15

    @staticmethod
    def calculate_bid(current_pos: tuple, pickup: tuple, dropoff: tuple, battery: float) -> tuple[float, bool]:
        dist_pickup = abs(current_pos[0] - pickup[0]) + abs(current_pos[1] - pickup[1])
        dist_dropoff = abs(pickup[0] - dropoff[0]) + abs(pickup[1] - dropoff[1])
        total_dist = dist_pickup + dist_dropoff
        energy_required = total_dist * TaskManager.ENERGY_PER_STEP

        predicted_remaining_battery = battery - energy_required
        if predicted_remaining_battery < 15.0:
            return (float('inf'), False)  # Refuse task to prevent mid-aisle stranding

        return (total_dist, True)