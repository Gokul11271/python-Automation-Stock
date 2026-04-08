import pygame
import random

pygame.init()

# Screen
WIDTH, HEIGHT = 800, 500
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Nature Game")

# Player
player_x, player_y = 400, 250
speed = 5

# Colors
GREEN = (34, 139, 34)
BLUE = (135, 206, 235)
BROWN = (139, 69, 19)
WHITE = (255, 255, 255)

# Trees
trees = [(random.randint(0, 2000), random.randint(0, 2000)) for _ in range(30)]

# Animals
animals = [(random.randint(0, 2000), random.randint(0, 2000)) for _ in range(10)]

# Camera
camera_x, camera_y = 0, 0

clock = pygame.time.Clock()
running = True

while running:
    clock.tick(60)

    # Sky
    screen.fill(BLUE)

    # Events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Movement
    keys = pygame.key.get_pressed()
    if keys[pygame.K_w]:
        player_y -= speed
    if keys[pygame.K_s]:
        player_y += speed
    if keys[pygame.K_a]:
        player_x -= speed
    if keys[pygame.K_d]:
        player_x += speed

    # Camera follow
    camera_x = player_x - WIDTH // 2
    camera_y = player_y - HEIGHT // 2

    # Ground
    pygame.draw.rect(screen, GREEN, (0, 0, WIDTH, HEIGHT))

    # Trees
    for tree in trees:
        pygame.draw.rect(screen, BROWN,
                         (tree[0] - camera_x, tree[1] - camera_y, 20, 40))

    # Animals
    for animal in animals:
        pygame.draw.circle(screen, WHITE,
                           (animal[0] - camera_x, animal[1] - camera_y), 8)

    # Player (center)
    pygame.draw.rect(screen, (255, 0, 0),
                     (WIDTH//2, HEIGHT//2, 20, 20))

    pygame.display.update()

pygame.quit()