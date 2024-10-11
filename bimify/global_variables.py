import os

root_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # "04_polygonization"
models_root_folder = os.path.join(root_folder, "resources") # root_folder

# Paramètres géénraux du plan analysé
resolution_dpi = 144 # résolution de l'image en dpi
plan_scale = 0.01
normalized_scale = 100 
rescale_factor_for_cart_locate = 4
resolution_pixel_par_metre = (resolution_dpi / 2.54) * 100 * plan_scale # résolution de l'image en pixels par mètre réel

global_scale = 2 # échelle globale pour le traitement des polygones en pixels
scale_2d_to_ifc = 1 / (resolution_pixel_par_metre * global_scale)  # échelle du plan = 0.0088 (unité IFC : m)


# Paramètres pour conversion des lignes directrices en murs
angle_eps = 3 * (3.1416/180) # écart d'angle en radian pour considérer deux lignes comme parallèles
max_wall_width = 70 * global_scale # largeur maximale d'un mur en pixels

# Paramètres pour le traitement des murs
intersection_threshold = 0.4 # seuil de recouvrement pour considérer deux murs comme se croisant et dont le plus petit sera supprimé
epsilon_deg = 6 # écart d'angle en degrés pour orthogonaliser les murs
shorter_length_threshold = 50 * global_scale # distance en pixels sous laquelle epsilon_deg est multiplié par 2 (pour davantage orthogonaliser les murs courts)

# Connexion des murs et création des nodes
join_max_length = 0.4 / scale_2d_to_ifc # 30 * global_scale # distance maximale en pixels à ajouter pour rencontrer le point d'intersection et connecter les murs
cut_max_length = 0.3 / scale_2d_to_ifc # 30 * global_scale # distance maximale à couper pour nettoyer les bouts de murs qui dépassent d'un angle


# Paramètres pour le traitement des pièces
min_room_area = 0.03 / (scale_2d_to_ifc**2) # surface minimale d'une pièce en m²
max_gt_area = 1.0 / (scale_2d_to_ifc**2)
ocr_conf = 0.2 # seuil de confiance pour lire une étiquette de pièce avec OCR

# Paramètres pour la détection des objets, dimensions en mètres, puis conversion en unité 2d
min_score_for_objects_detection = 0.2

shortest_door_width = 0.6 / scale_2d_to_ifc # largeur minimale d'une porte pour être détectée
shortest_edge_length_default = 0.2 / scale_2d_to_ifc # longueur minimale du petit côté d'un objet pour être détecté
shortest_edge_length_wc = 0.25 / scale_2d_to_ifc
shortest_edge_length_sink = 0.2 / scale_2d_to_ifc
shortest_edge_length_shower = 0.45 / scale_2d_to_ifc
shortest_edge_length_bath = 0.5 / scale_2d_to_ifc
shortest_edge_length_bed = 0.7 / scale_2d_to_ifc
shortest_long_edge_length_bed = 1.7 / scale_2d_to_ifc


# Modélisation IFC, dimensions en mm
default_wall_height = 2800 # hauteur des étages
default_space_height = 2600 # hauteur des espaces
default_door_height = 2200 # hauteur des portes
default_opening_thickness = 40 # épaisseur des portes et fenêtres
default_window_height = 1400 # hauteur des fenêtres
default_window_sill_height = 800 # hauteur des appuis de fenêtres
default_generic_obj_height = 800 # hauteur des objets génériques
default_slab_thickness = 200 # épaisseur des dalles

default_outlet_height = 300 # hauteur des prises électriques



# Prédiction des objets :
objects_class_map = {
    "door": 0,
    "window": 1,
    "wc": 2,
    "sink": 3,
    "shower": 4,
    "bath": 5,
    "bed": 6,
}



colors = [
        (0, 0, 255),      # Rouge
        (0, 255, 0),      # Vert
        (255, 0, 0),      # Bleu
        (0, 200, 200),    # Jaune
        (255, 0, 255),    # Magenta
        (255, 255, 0),    # Cyan
        (0, 64, 192),    # Orange
        (0, 128, 64),     # Vert olive
        (16, 64, 16),      # Vert foncé
        (64, 16, 16),      # Bleu marine
        (64, 16, 64),    # Pourpre
        (0, 16, 64),   # Marron
        (16, 16, 64),      # Rouge foncé
        (16, 64, 64),    # Jaune foncé
        (64, 16, 64),    # Magenta foncé
        (64, 64, 16),    # Cyan foncé
    ]

