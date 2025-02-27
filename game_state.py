class GameState:
    def __init__(self):
        self.player_1 = Player()
        self.player_2 = Player()

    def __str__(self):
        return str(self.to_dict())

    def to_dict(self) -> dict[str, dict[str, int]]:
        data = {'p1': self.player_1.to_dict(), 'p2': self.player_2.to_dict()}
        return data

    def _init_player (self, player_id, bullets_remaining, bombs_remaining, hp,
                      num_deaths, num_unused_shield, shield_health):
        if player_id == 1:
            player = self.player_1
        else:
            player = self.player_2
        player.set_state(bullets_remaining, bombs_remaining, hp, num_deaths,
                         num_unused_shield, shield_health)

    def perform_action(self, action, player_id, fov):
        """use the user sent action to alter the game state"""

        # perform sanity check to see if our function handles all the actions
        all_actions = {"gun", "shield", "bomb", "reload", "badminton", "golf", "fencing", "boxing"}

        if player_id == 1:
            attacker            = self.player_1
            opponent            = self.player_2
        else:
            attacker            = self.player_2
            opponent            = self.player_1

        can_see = fov
        attacker.rain_damage(opponent, can_see)

        # perform the actual action
        if action == "gun":
            attacker.shoot(opponent)
        elif action == "shield":
            attacker.shield()
        elif action == "reload":
            attacker.reload()
        elif action == "bomb":
            attacker.bomb(opponent, can_see)
        elif action in {"badminton", "golf", "fencing", "boxing"}:
            # all these have the same behaviour
            attacker.harm_AI(opponent, can_see)
        elif action == "logout":
            # has no change in game state
            pass
        else:
            # invalid action we do nothing
            pass

class Player:
    def __init__(self):
        # Constants
        self.max_bombs          = 2
        self.max_shields        = 3
        self.hp_bullet          = 5
        self.hp_AI              = 10 
        self.hp_bomb            = 5
        self.hp_rain            = 5
        self.max_shield_health  = 30
        self.max_bullets        = 6
        self.max_hp             = 100

        # Initial state
        self.hp = self.max_hp
        self.num_bullets = self.max_bullets
        self.num_bombs = self.max_bombs
        self.hp_shield = 0
        self.num_deaths = 0
        self.num_shield = self.max_shields

        self.rain_list = []  # list of quadrants where rain/snow has been started by the bomb of this player

    def __str__(self):
        return str(self.to_dict())

    def to_dict(self) -> dict[str, int]:
        data = dict()
        data['hp']              = self.hp
        data['bullets']         = self.num_bullets
        data['bombs']           = self.num_bombs
        data['shield_hp']       = self.hp_shield
        data['deaths']          = self.num_deaths
        data['shields']         = self.num_shield
        return data

    def set_state(self, bullets_remaining: int, bombs_remaining: int, hp: int, num_deaths: int, num_unused_shield: int, shield_health: int) -> None:
        self.hp             = hp
        self.num_bullets    = bullets_remaining
        self.num_bombs      = bombs_remaining
        self.hp_shield      = shield_health
        self.num_shield     = num_unused_shield
        self.num_deaths     = num_deaths

    #TODO: Attain ammo data from the gun packet + Health from health packet
    def shoot(self, opponent):
        if self.num_bullets <= 0:
            return
        self.num_bullets -= 1
        opponent.damage(self.hp_bullet)

    def damage(self, hp_reduction: int) -> None:
        # use the shield to protect the player
        if self.hp_shield > 0:
            new_hp_shield  = max(0, self.hp_shield - hp_reduction)
            # If damage is more than the shield, induce the remaining damage
            hp_reduction   = max(0, hp_reduction - self.hp_shield)
            self.hp_shield = new_hp_shield

        # reduce the player HP
        self.hp = max(0, self.hp - hp_reduction)
        if self.hp == 0:
            # if we die, we spawn immediately
            self.num_deaths += 1
            self.set_state(self.max_bullets, self.max_bombs, self.max_hp, self.num_deaths, self.max_shields, 0)

    def shield(self):
        """Activate shield"""
        if self.num_shield <= 0 or self.hp_shield > 0:
            return
        self.hp_shield = self.max_shield_health
        self.num_shield -= 1

    #TODO: Implement bomb, add the start to a rain/snow in the quadrant of the opponent
    def bomb(self, opponent, can_see):
        """Throw a bomb at opponent"""
        while True:
            # check the ammo
            if self.num_bombs <= 0:
                break
            self.num_bombs -= 1

            # check if the opponent is visible
            if not can_see:
                # this bomb will not start a rain/snow and hence has no effect with respect to gameplay
                break

            opponent.damage(self.hp_bomb)
            break

    #TODO: Implement rain_damage
    def rain_damage(self, opponent, can_see):
        """
        Whenever an opponent walks into a quadrant we need to reduce the health
        based on the number of rains/snow
        """
        if can_see:
            for p in self.rain_list:
                opponent.damage(self.hp_rain)

    def harm_AI(self, opponent, can_see):
        """ We can harm am opponent based on our AI action if we can see them"""
        if can_see:
            opponent.damage(self.hp_AI)

    def reload(self):
        """ perform reload only if the magazine is empty"""
        if self.num_bullets <= 0:
            self.num_bullets = self.max_bullets
