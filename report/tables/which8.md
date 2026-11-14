| Sensor set                      | Chosen by                      | Test RMSE    |   Gap to 21 | Within 1.0   | Phase          |
|:--------------------------------|:-------------------------------|:-------------|------------:|:-------------|:---------------|
| all 21 sensors                  | all                            | 12.99 ± 0.07 |        0    |              | pre-registered |
| 8 ranked sensors                | pre-registered ranking (train) | 15.56 ± 0.06 |        2.57 | no           | pre-registered |
| 8 sensors, greedy on validation | forward selection (validation) | 13.88 ± 0.12 |        0.89 | yes          | post hoc       |
| 8 random sensors (3 draws)      | random                         | 14.74 ± 0.77 |        1.75 | no           | post hoc       |
| 8 lowest-ranked sensors         | bottom of the ranking          | 13.96 ± 0.07 |        0.97 | yes          | post hoc       |