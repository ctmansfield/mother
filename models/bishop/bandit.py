import random


class BetaArm:
    def __init__(self, a=1.0, b=1.0):
        self.a, self.b = a, b

    def sample(self):
        x = random.gammavariate(self.a, 1.0)
        y = random.gammavariate(self.b, 1.0)
        return x / (x + y) if (x + y) > 0 else 0.5

    def update(self, reward: float):
        self.a += reward
        self.b += 1 - reward


class BishopBandit:
    def __init__(self, arms):
        self.arms = {arm: BetaArm() for arm in arms}

    def select(self):
        return max(self.arms.items(), key=lambda kv: kv[1].sample())[0]

    def update(self, arm, reward):
        self.arms[arm].update(reward)
