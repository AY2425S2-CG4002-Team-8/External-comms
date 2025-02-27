import asyncio
import json

from logger import get_logger

logger = get_logger(__name__)

class AiEngine:
    def __init__(self, read_buffer, write_buffer):
        self.PREDICTION_DATA_POINTS = 50
        self.read_buffer = read_buffer
        self.write_buffer = write_buffer
        self.hardcoded_sensor_data = {
            "badminton": {
                'ax': [-1870, -3117, 0, -1725, -1828, -1828, -1828, -1828, -1828, -1828, -1240, -1078, -1056, -982, -868, -758,
                    -667, -504, -448, -355, -206, -49, 39, 109, 88, 111, 108, -1, -99, -192, -300, -335, -374, -806, -1201, -801,
                    -542, -350, -239, -126, -97, -86, -79, -66, -34, -14, 22, 36, 16, -8],
                'ay': [-151, -579, 0, 772, 129, 129, 129, 129, 129, 129, 137, 262, 420, 390, 461, 382, 314, 242, 145, 68, -77, -251,
                    -382, -456, -362, -229, -165, -112, -59, 8, 98, 75, -80, -168, -745, -342, 243, -109, -299, -176, -108, -138,
                    -86, -30, -25, -63, -125, -146, -85, -37],
                'az': [-1477, -1595, 0, 859, 619, 619, 619, 619, 619, 619, 449, 429, 528, 446, 339, 255, 19, -161, -374, -647, -848,
                    -1006, -1069, -996, -880, -753, -642, -653, -477, -416, -335, -262, -145, -160, 776, 1229, 1114, 715, 581,
                    509, 488, 503, 496, 443, 374, 323, 283, 245, 179, 123],
                'gx': [-7523, -9907, 0, -3564, -7668, -7668, -7668, -7668, -7668, -7668, 4956, 5113, 3592, 2881, 2080, -823, -3180,
                    -4358, -3396, -2639, 145, 1580, 161, -239, 1477, 1522, 1599, 1002, -431, 187, -1404, -6316, -9900, -13842,
                    -3527, 3641, 262, -1564, 2245, 2412, -1849, -2546, -862, 76, 718, 1804, 4123, 6826, 8457, 9470],
                'gy': [25000, 25000, 0, 21893, -5829, -5829, -5829, -5829, -5829, -5829, -25000, -25000, -25000, -25000, -25000,
                    -25000, -25000, -25000, -25000, -25000, -19470, -12949, -6954, -1033, 3574, 6527, 8770, 11057, 14386, 17638,
                    22202, 25000, 25000, 25000, 25000, 21552, 1918, -6567, -6805, -3303, -1146, -1108, -2301, -4055, -5314,
                    -6123, -6492, -6723, -6936, -6865],
                'gz': [-14651, -16055, 0, -14263, 976, 976, 976, 976, 976, 976, 8913, 9678, 10546, 10861, 11781, 13059, 13178,
                    12285, 13324, 12775, 12592, 10952, 7471, 2889, -1978, -4869, -6067, -6436, -6742, -6513, -5137, -3133, 281,
                    2050, -4821, -13415, -4630, 6730, 8004, 3022, -583, -1586, -1189, 389, 1775, 2659, 4089, 4911, 4242, 3128]
            },
            "boxing": {
                'ax': [-1441, -2094, -3384, -3735, -3257, -2508, -1924, -1690, -1563, -1207, -856, -694, -561, -440, -349, -264,
                    -226, -281, -373, -525, -749, -1089, -1375, -1807, -2484, -3089, -3093, -2498, -1849, -1298, -890, -650,
                    -478, -392, -287, -185, -122, -65, -46, 11, -12, -73, -72, -156, -227, -251, -376, -424, -552, -729],
                'ay': [-407, -314, -508, -342, -69, 193, 327, 191, -116, -8, 118, 88, 93, 114, 168, 217, 185, 152, 190, 189, 126,
                    159, 26, 45, 68, 100, 110, -31, 15, 68, 86, 62, 63, 62, 6, -7, 54, 18, 17, 61, 135, 202, 168, 228, 291, 298,
                    374, 454, 395, 374],
                'az': [453, 144, -1026, -1114, -1039, -788, -381, 138, 10, -171, -232, -219, -163, -213, -315, -388, -462, -449,
                    -407, -381, -386, -474, -601, -674, -783, -889, -725, -494, -90, 22, -56, -50, -70, -66, -78, -69, -47, -56,
                    -89, -103, -114, -125, -133, -133, -151, -166, -208, -171, -145, -172],
                'gx': [7455, 5481, 3527, 10094, 4187, -4425, 2701, 109, -1415, 2405, 2819, 2252, 1828, 590, 605, -398, -1487, -1038,
                    -387, -2387, -3475, -4193, -3460, -1100, -426, 76, -665, 1890, 2616, -1207, -4015, -5141, -5368, -6004,
                    -6604, -5383, -5440, -6861, -6443, -4526, -2426, -2654, -2579, -1272, -1905, -2315, -2951, -5250, -6102,
                    -2927],
                'gy': [-8874, -25000, -25000, -25000, -25000, -25000, -19806, -12050, -14402, -16079, -12754, -9229, -7528, -7206,
                    -6214, -4968, -1123, 3111, 7238, 10809, 13609, 14963, 15815, 23423, 25000, 25000, 25000, 25000, 24779, 15518,
                    7533, 4673, 5574, 6002, 5068, 4021, 3444, 1876, -711, -2045, -2639, -3199, -3366, -4216, -5230, -5633, -6444,
                    -6026, -4280, -5417],
                'gz': [-4662, 344, -129, -2536, -5365, -11799, -8430, -4362, -5153, -6189, -5001, -3474, -3027, -2515, -1252, 116,
                    1571, 2716, 3792, 4208, 4597, 6218, 8432, 9647, 9920, 9626, 8401, 8025, 5761, 2439, 2340, 2399, 1930, 1950,
                    1779, 1264, 640, -176, -971, -1869, -2973, -4170, -5080, -6505, -8357, -9330, -10750, -13420, -14516, -14394]
            },
            "reload":{
                'ax': [929, 2388, 763, 470, 279, 257, 257, 257, 384, 384, 165, 145, 42, -24, -205, -171, -228, -234, -114, -14, -48,
                    -5, -23, -6, 3, -15, -13, -5, -9, 6, 19, 0, -1, 23, 11, 29, 34, 29, 46, 43, 16, 6, 25, 27, 17, 7, 14, 10, 13,
                    16],
                'ay': [-84, -1161, -568, -217, 19, 311, 311, 311, 53, 53, 256, 326, 513, 380, 607, 498, 500, 801, 656, 435, 558,
                    563, 546, 534, 574, 545, 520, 520, 497, 497, 495, 496, 510, 494, 477, 472, 500, 491, 476, 482, 474, 475, 482,
                    452, 496, 510, 511, 506, 519, 509],
                'az': [-235, -255, 344, 452, 422, 318, 318, 318, 180, 180, 222, 175, 241, 128, 82, 3, -41, 23, -25, -67, -5, 8, 26,
                    -23, -50, -47, -48, -48, -61, -69, -69, -48, -45, -62, -56, -56, -48, -36, -51, -58, -59, -64, -64, -62, -53,
                    -47, -53, -63, -64, -70],
                'gx': [-8354, 8476, -836, -6861, 4249, 7772, 7772, 7772, 11615, 11615, 16171, 17553, 12662, 9521, 8574, 1686, 5140,
                    3830, -1464, 378, 2945, 1481, 1196, 997, 604, 223, 167, 341, 501, 12, -50, 336, 20, -184, -20, 446, 383,
                    -135, -85, 175, -164, 52, -276, -12, 283, -70, 54, 30, 348, 521],
                'gy': [-10312, 473, 4694, -997, -2565, -4788, -4788, -4788, -1699, -1699, 306, -170, 693, -1026, -2850, -2577, -663,
                    -1022, -2175, -660, 352, 318, -202, -797, -582, -194, -390, -321, -163, -238, 300, 447, -280, -321, 123, 32,
                    172, -125, -364, -51, 55, -161, -48, 43, -26, -305, -280, -29, 6, 307],
                'gz': [7473, 16858, 316, -10143, -3334, 286, 286, 286, 923, 923, -773, -2120, -7091, -7676, -5670, -6913, -7036,
                    -5287, -1533, -1038, -1614, -157, 199, -276, -24, 454, 306, 598, 803, 389, 454, 599, 469, 737, 700, 357, 247,
                    156, -119, -67, -58, -80, 23, -304, -582, -421, -427, -546, -404, -222]
            },
            "golf": {
                'ax': [-678, -241, -230, -196, -91, -100, -138, -142, -217, -423, -585, -729, -957, -1211, -1320, -1402, -1309,
                    -1099, -1004, -982, -991, -1030, -1061, -1098, -1187, -1173, -1054, -935, -788, -631, -493, -428, -327, -259,
                    -157, -124, -115, -142, -176, -201, -318, -331, -328, -408, -509, -564, -763, -836, -895, -901],
                'ay': [157, -49, 171, -111, -223, -203, -278, -396, -363, -274, -269, -253, -212, -233, -23, 164, 353, 288, 260,
                    445, 624, 582, 339, 245, 121, -30, -107, -270, -342, -389, -368, -352, -280, -252, -177, -122, -98, -29, -55,
                    46, 66, -1, 15, 33, -40, 9, 7, 97, 156, 131],
                'az': [933, 6, -93, -58, 33, 97, 116, 79, 49, 35, -3, -18, -26, -108, -224, -269, -358, -322, -218, -284, -364,
                    -289, -240, -313, -343, -297, -239, -179, -129, -90, -48, -2, 40, 28, 4, -8, 19, 19, 22, 86, 126, 111, 60,
                    46, 40, 70, 85, 86, 69, 60],
                'gx': [-5208, 10215, 3291, -3450, -1668, -865, -2384, -2925, -1361, -714, -762, 73, 909, 3509, 5597, 5249, 4210,
                    1217, 1712, 2787, 3125, 748, -1136, -1786, -2958, -3198, -3778, -4087, -3423, -4057, -3578, -3024, -2507,
                    -1577, -992, -987, -484, 91, 342, -1364, -2720, -3375, -3431, -4528, -3261, -1510, 328, 483, -1648, -2467],
                'gy': [-3859, -1966, 921, 756, 593, 450, -1290, -2555, -1978, -1805, -2456, -1670, -522, -377, -455, -260, -2701,
                    -3253, -1860, -1029, 1130, 2452, 1969, 2527, 3473, 3989, 4010, 4186, 3781, 3050, 2730, 1733, -212, -1336,
                    -978, 254, 1029, 1017, 785, 399, -2020, -4224, -4708, -3767, -3148, -1831, -939, -2190, -3011, -3334],
                'gz': [9458, 10419, 7287, 3388, 2253, 1484, -550, -3978, -7455, -9782, -12395, -15255, -17563, -19762, -20825,
                    -18987, -13039, -8590, -6186, -4635, -1532, 3537, 6829, 8587, 10862, 12778, 13557, 13902, 13068, 11378, 9449,
                    8188, 7263, 6384, 4346, 1821, 468, -680, -1553, -1586, -1268, -2117, -2611, -3627, -5175, -7430, -9506,
                    -10625, -11217, -10853]
            },
            "bomb": {
                'ax': [-2504, -3128, -3408, -1592, -1200, -1073, -782, -530, -425, -357, -359, -315, -314, -270, -261, -264, -290,
                    -309, -305, -308, -290, -244, -273, -508, -905, -1632, -1686, -1036, -406, -261, 3, 22, -82, -60, -128, -131,
                    -128, -159, -143, -227, -265, -203, -406, -439, -519, -774, -822, -864, -958, -891],
                'ay': [312, 258, -673, 270, -105, 183, 148, -161, -204, -221, -298, -349, -431, -493, -581, -624, -550, -487, -377,
                    -318, -232, -214, -104, 19, 37, -67, -51, -354, -5, 89, -206, -159, -110, -38, 45, 5, -5, -5, 2, 84, 79, 94,
                    198, 216, 206, 284, 371, 386, 357, 476],
                'az': [-70, -214, -689, -819, -621, -680, -635, -685, -585, -466, -411, -388, -484, -589, -693, -792, -799, -811,
                    -844, -825, -828, -857, -839, -755, -622, -363, 814, 1397, 1077, 780, 489, 494, 482, 397, 365, 245, 178, 143,
                    114, 133, 105, 108, 159, 149, 206, 211, 173, 166, 145, 157],
                'gx': [-12720, -13727, 7447, 2836, -2713, 6534, -688, -828, 1563, 1297, 1409, 1166, 1625, 1229, -448, -1283, -1990,
                    -3036, -2839, -2396, -3246, -2750, -1603, -680, -3805, -9409, -21521, -25000, -5037, 2943, 4183, 4540, 2851,
                    3732, 2179, 1158, 3848, 6528, 9073, 8938, 8183, 9103, 6064, 4696, 5867, 6872, 6822, 5881, 6942, 8590],
                'gy': [-25000, -25000, -25000, -25000, -25000, -22259, -16924, -11129, -6552, -3891, -2898, -3342, -4013, -3776,
                    -2597, -851, 1768, 3530, 5800, 8811, 11619, 16008, 21736, 25000, 25000, 25000, 25000, 25000, 2104, -3526,
                    -398, 3899, 4857, 2183, 828, -150, -611, 199, 1075, 2403, 2867, 4456, 5893, 6111, 8404, 8548, 6434, 5968,
                    6360, 5197],
                'gz': [14419, 11910, 15684, 22456, 14831, 12478, 15876, 15279, 12899, 10338, 7712, 5412, 3128, 1007, -1049, -4636,
                    -8153, -10225, -12873, -13731, -14147, -15723, -17044, -17299, -15940, -15681, -14072, -15161, -7055, 3889,
                    7683, 3887, 1497, 1319, 708, 1014, 1968, 2217, 2190, 577, -1500, -3269, -6635, -9218, -9498, -10910, -12619,
                    -12420, -12276, -11221]
            },
            "shield": {
                'ax': [-870, -1211, -1978, -2966, -2560, -1745, -1098, -841, -999, -295, 115, 296, 281, 194, 195, 358, 328, 315,
                    329, 338, 358, 365, 354, 359, 348, 339, 353, 355, 338, 333, 337, 338, 345, 349, 331, 331, 334, 319, 287, 263,
                    182, 3, -173, -296, -383, -478, -646, -833, -920, -1070],
                'ay': [1451, 1669, 1533, 1770, 649, -152, -83, -154, -234, -316, 123, -85, 73, 36, 20, 272, 115, 139, 162, 155, 242,
                    182, 241, 202, 173, 202, 204, 202, 200, 193, 180, 196, 196, 185, 180, 180, 177, 169, 147, 131, 11, -257,
                    -400, -360, -142, 41, 177, 342, 467, 569],
                'az': [-771, -1178, -1329, -770, -266, 78, 114, 215, 754, 412, 3, -108, 84, 315, 339, 203, 214, 265, 280, 264, 274,
                    298, 305, 295, 295, 279, 266, 287, 302, 320, 315, 287, 293, 298, 305, 303, 291, 301, 312, 307, 331, 332, 251,
                    88, -64, -111, -90, -93, -54, -48],
                'gx': [2734, 6028, 6888, 1372, -6861, -7222, -4062, -5838, -9517, -5703, -1591, -3283, -159, -4220, 793, 40, -920,
                    -344, -666, -447, 578, 84, 362, -298, 212, -249, 9, 246, -152, -131, 40, 186, -480, -241, -65, 67, -323,
                    -103, -130, 311, 52, 426, 79, 679, 1582, 2827, 3332, 4941, 5274, 6015],
                'gy': [-3094, -431, 19942, 25000, 25000, 22225, 17416, 16679, 13661, 2190, -537, 1480, 2361, 3912, 43, -466, 701,
                    343, 244, 116, 299, 527, 381, 267, 211, 196, 261, 664, 656, 215, 148, 6, 131, 318, 344, -48, -49, 57, -124,
                    -518, -669, -1458, -3259, -5664, -6079, -4366, -2417, -2281, -1834, -703],
                'gz': [8436, 22963, 25000, 25000, 25000, 25000, 19266, 14587, 9875, 5639, 4641, 3234, 2500, 1638, 887, 817, 541,
                    327, -83, -660, -361, -315, -371, -37, -113, -142, -70, -77, -27, 65, -2, 31, 27, -161, -177, -162, -183,
                    -247, -363, -747, -1494, -3861, -7692, -12406, -16904, -20004, -21870, -24552, -24678, -23794]
            },
            "fencing": {
                'ax': [-2106, -2301, -2315, -1956, -1500, -1143, -829, -532, -353, -283, -289, -279, -316, -388, -495, -661, -908,
                    -1188, -1732, -1897, -1839, -1516, -1138, -1120, -1086, -1010, -920, -722, -501, -317, -221, -163, -91, -79,
                    -118, -174, -225, -284, -443, -642, -965, -1371, -1781, -2271, -2099, -1728, -1257, -1165, -1101, -907],
                'ay': [1236, 1393, 1166, 658, 299, -33, -372, -589, -641, -680, -671, -603, -501, -428, -412, -369, -329, 58, 89,
                    344, 1296, 1073, 1321, 1492, 1555, 1336, 910, 574, 280, 50, -97, -205, -326, -370, -325, -252, -263, -270,
                    -199, -147, -166, 6, 82, 254, 652, 738, 613, 202, 62, 168],
                'az': [-309, -157, -4, 172, 233, 199, 83, -26, -107, -156, -205, -237, -236, -231, -323, -368, -446, -533, -473,
                    -563, -795, -970, -841, -601, -409, -270, -171, -145, -126, -73, -7, 33, 16, -18, -27, -25, -47, -70, -53,
                    -65, -128, -219, -273, -320, -313, -196, -165, -53, -1, -23],
                'gx': [23178, 13109, -705, -5795, -7377, -9097, -6974, -2773, -871, 920, 3979, 7595, 9002, 6864, 5701, 5816, 8539,
                    10769, 6651, 6279, -17531, -25000, -19792, -9445, -12721, -20616, -24712, -25000, -25000, -23681, -19804,
                    -16496, -12804, -7088, -3211, -2305, -1754, 173, 2091, 2462, 5244, 9939, 11468, 14057, 3955, -6521, -7714,
                    -32, 6402, 8973],
                'gy': [14326, 22564, 23677, 18314, 12045, 5027, 260, -2475, -3663, -4087, -4958, -5387, -5514, -5693, -6323, -6828,
                    -7962, -8686, -9508, -12693, -9765, -5012, 1945, 11281, 13652, 11858, 5909, -1683, -6131, -6546, -5664,
                    -5769, -5541, -4581, -2940, -2858, -2950, -2118, -1033, -503, -660, -1481, -1373, -2201, -3738, 1872, 3080,
                    4540, 4538, 4096],
                'gz': [25000, 25000, 25000, 25000, 25000, 25000, 25000, 19420, 11616, 5048, -750, -7232, -11870, -15970, -20597,
                    -25000, -25000, -25000, -25000, -25000, -25000, -25000, -14746, -1707, 4950, 11033, 17381, 19299, 19060,
                    16450, 13283, 9179, 4846, -369, -4821, -8249, -11559, -15140, -18815, -23139, -25000, -25000, -25000, -25000,
                    -25000, -25000, -18650, -5284, -4506, -8913]
            },
            "gun": {
                'ax': [-1586, 0, -2250, -1668, -1166, -721, -588, -595, -553, -470, -427, -418, -449, -482, -517, -540, -524, -486,
                    -459, -457, -462, -467, -470, -467, -466, -463, -482, -495, -492, -459, -437, -444, -458, -479, -491, -496,
                    -488, -467, -450, -448, -463, -481, -499, -485, -459, -456, -461, -461, -465, -475],
                'ay': [104, 0, 1198, 1242, 1009, 1031, 749, 528, 393, 323, 270, 231, 202, 168, 150, 110, 67, 45, 49, 48, 40, 47, 59,
                    73, 97, 123, 139, 161, 178, 189, 194, 179, 156, 148, 159, 161, 155, 157, 142, 127, 118, 116, 125, 136, 132,
                    119, 109, 109, 121, 137],
                'az': [-530, 0, -368, -209, -291, -241, -80, 41, 67, 3, -69, -98, -85, -56, -34, -22, -11, -6, 2, 10, 6, 0, 3, -3,
                    4, 0, -6, -3, -2, 0, 1, 12, 11, 3, 1, 2, -2, -9, -16, -15, -18, -21, -18, -7, 0, 9, 9, 1, 0, 0],
                'gx': [16036, 0, 161, -4390, -160, 5694, 6508, 5607, 4491, 2748, 280, -916, -590, 722, 1516, 1680, 1566, 1228, 538,
                    -442, -997, -1227, -1337, -1194, -988, -1063, -785, -587, -283, 349, 489, 198, -131, -40, 126, 89, 109, 205,
                    242, 399, 297, 56, -68, -242, -288, -301, -90, 232, 119, -190],
                'gy': [-5587, 0, -4099, -7079, -7843, -3358, 2428, 3807, 1404, -1573, -2708, -1994, -680, 251, 486, 446, 594, 653,
                    524, 427, 196, 44, 22, 86, 39, -45, -94, -60, -20, 19, 108, 62, -116, -80, -77, -96, -61, -128, -155, -149,
                    -131, -79, 31, 202, 232, 231, 74, -96, -80, 10],
                'gz': [-25000, 0, -25000, -22698, -15440, -8144, -730, 1754, 2097, 1882, 1357, 804, 1134, 2375, 3162, 3730, 3911,
                    3303, 2616, 1853, 1240, 589, -47, -627, -1039, -1467, -1601, -1715, -1631, -1110, -445, -138, -91, -205,
                    -132, 39, 105, 325, 572, 734, 629, 355, 143, 108, 216, 226, 172, 82, -170, -370]
            }
        }

    def get_data(self, data) -> dict[str, list[int]]:
        """
        Converts a list of PacketImu objects into a combined input list for the AI.
        """
        ax_array, ay_array, az_array = [], [], []
        gx_array, gy_array, gz_array = [], [], []

        for packet in data:
            # Gets integer from bytes. Little endian as defined by relay node and signed since values can be -ve
            ax = int.from_bytes(packet.ax, byteorder='little', signed=True)
            ay = int.from_bytes(packet.ay, byteorder='little', signed=True)
            az = int.from_bytes(packet.az, byteorder='little', signed=True)
            gx = int.from_bytes(packet.gx, byteorder='little', signed=True)
            gy = int.from_bytes(packet.gy, byteorder='little', signed=True)
            gz = int.from_bytes(packet.gz, byteorder='little', signed=True)

            ax_array.append(ax)
            ay_array.append(ay)
            az_array.append(az)
            gx_array.append(gx)
            gy_array.append(gy)
            gz_array.append(gz)

        return {
            'ax': ax_array,
            'ay': ay_array,
            'az': az_array,
            'gx': gx_array,
            'gy': gy_array,
            'gz': gz_array
        }
    
    def classify(self, data: json) -> str:
        """
        Matches read_buffer against predefined sensor data using exact comparison.
        """
        for action, sensor_data in self.hardcoded_sensor_data.items():
            if all(
                data.get(axis) == sensor_data[axis]
                for axis in sensor_data
            ):
                return action

        return None
    
    async def run(self):
        await asyncio.gather(
            self.predict()
        )

    async def predict(self):
        """
        Collects self.PREDICTION_DATA_POINTS packets to form a dictionary of arrays (current implementation) for AI inference
        AI inference is against hardcoded dummy IMU data
        """
        data = []
        try:
            while True:
                data.clear()
                while len(data) < self.PREDICTION_DATA_POINTS:
                    packet = await self.read_buffer.get()
                    data.append(packet)
                    logger.debug(f"IMU packet: {packet}. Received: {len(data)}/{self.PREDICTION_DATA_POINTS}")

                if len(data) != self.PREDICTION_DATA_POINTS:
                    logger.debug(f"Packet size of {self.PREDICTION_DATA_POINTS} was not received")
                    continue
                
                data_dictionary = self.get_data(data)
                predicted_data = self.classify(data_dictionary)
                logger.debug(f"AI Engine Prediction: {predicted_data}")
                await self.write_buffer.put(predicted_data)

        except Exception as e:
            logger.error(f"Error occurred in the AI Engine: {e}")
